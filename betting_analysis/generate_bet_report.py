#!/usr/bin/env python3

import argparse
import csv
import datetime as dt
import html
import json
import math
import os
import re
import ssl
import tempfile
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Bet:
    date: dt.date
    pick: str
    odds_american: Optional[float]
    risk: float
    to_win: float
    result: str
    net: float
    book: str
    league: str
    bet_type: str


LEAGUE_COLOR_MAP = {
    "NHL": "#1D4ED8",
    "NCAAB": "#D97706",
    "NBA": "#6366F1",
    "NFL": "#013369",
    "MLB": "#0477BF",
    "NCAAF": "#B89145",
    "PGA": "#64748B",
    "OTHER": "#6B7280",
    "CROSSSPORT": "#8B5CF6",
}


# Brighter, distinct accents for the dark card surface and its league filters.
LEAGUE_CARD_COLOR_MAP = {
    "NFL": "#60A5FA",
    "NCAAF": "#F472B6",
    "NBA": "#FB923C",
    "NCAAB": "#A78BFA",
    "NHL": "#67E8F9",
    "MLB": "#2DD4BF",
    "PGA": "#A3E635",
    "CROSSSPORT": "#CBD5E1",
    "OTHER": "#94A3B8",
}


BOOK_COLOR_MAP = {
    "FANDUEL": "#0077FF",
    "DRAFTKINGS": "#53B949",
    "CAESARS": "#C7A257",
    "BETMGM": "#C0A362",
    "MGM": "#C0A362",
    "FANATICS": "#E31837",
    "BET365": "#1E9B4F",
    "BALLYS": "#CC0033",
    "RIVERS": "#1D4ED8",
    "NOVIG": "#4F46E5",
    "PROPHETX": "#06B6D4",
    "SPORTTRADE": "#0EA5E9",
    "BOOKIE": "#7C3AED",
    "BM": "#64748B",
    "BOL": "#F97316",
    "BETONLINE": "#F97316",
    "BUCKEYE": "#DC2626",
}

LEAGUE_LOGO_MAP = {
    "NHL": "nhl.png",
    "NCAAB": "ncaab.png",
    "NBA": "nba.png",
    "NFL": "nfl.png",
    "MLB": "mlb.png",
    "NCAAF": "ncaaf.webp",
}

BOOK_LOGO_MAP = {
    "FANDUEL": "fanduel.png",
    "DRAFTKINGS": "draftkings.png",
    "CAESARS": "caesars.jpg",
    "BETMGM": "betmgm.png",
    "MGM": "betmgm.png",
    "BALLYS": "bally.png",
    "RIVERS": "rivers.png",
    "NOVIG": "novig.jpeg",
    "PROPHETX": "prophetx.png",
    "FANATICS": "fanatics.png",
    "KALSHI": "kalshi.png",
    "BOOKMAKER": "bookmaker.png",
    "BOOKIE": "bookmaker.png",
    "BM": "bookmaker.png",
    "BOL": "betonline.png",
    "BETONLINE": "betonline.png",
}


def _team_logo_map(league: str, teams: List[Tuple[str, ...]]) -> Dict[str, Tuple[str, str]]:
    """Map a pick abbreviation to (logo path under logos/, display name)."""
    mapping: Dict[str, Tuple[str, str]] = {}
    for team in teams:
        canonical, name, *aliases = team
        filename = f"teams/{league}/{canonical.lower()}.png"
        for abbr in (canonical, *aliases):
            mapping[abbr] = (filename, name)
    return mapping


# Paths are the 128px square PNGs in logos/teams/. Extra tokens are aliases
# that show up in the sheet. TBI is a one-off typo for Tampa Bay (TBI/NYI).
TEAM_LOGO_BY_LEAGUE: Dict[str, Dict[str, Tuple[str, str]]] = {
    "NHL": _team_logo_map(
        "nhl",
        [
            ("ANA", "Anaheim Ducks"),
            ("BOS", "Boston Bruins"),
            ("BUF", "Buffalo Sabres"),
            ("CGY", "Calgary Flames"),
            ("CAR", "Carolina Hurricanes"),
            ("CHI", "Chicago Blackhawks"),
            ("COL", "Colorado Avalanche"),
            ("CBJ", "Columbus Blue Jackets"),
            ("DAL", "Dallas Stars"),
            ("DET", "Detroit Red Wings"),
            ("EDM", "Edmonton Oilers"),
            ("FLA", "Florida Panthers"),
            ("LAK", "Los Angeles Kings", "LA"),
            ("MIN", "Minnesota Wild"),
            ("MTL", "Montreal Canadiens"),
            ("NSH", "Nashville Predators"),
            ("NJD", "New Jersey Devils", "NJ"),
            ("NYI", "New York Islanders"),
            ("NYR", "New York Rangers"),
            ("OTT", "Ottawa Senators"),
            ("PHI", "Philadelphia Flyers"),
            ("PIT", "Pittsburgh Penguins"),
            ("SJS", "San Jose Sharks", "SJ"),
            ("SEA", "Seattle Kraken"),
            ("STL", "St. Louis Blues"),
            ("TBL", "Tampa Bay Lightning", "TB", "TBI"),
            ("TOR", "Toronto Maple Leafs"),
            ("UTA", "Utah Mammoth", "UTAH"),
            ("VAN", "Vancouver Canucks"),
            ("VGK", "Vegas Golden Knights"),
            ("WPG", "Winnipeg Jets"),
            ("WSH", "Washington Capitals"),
        ],
    ),
    "NFL": _team_logo_map(
        "nfl",
        [
            ("ARI", "Arizona Cardinals"),
            ("ATL", "Atlanta Falcons"),
            ("BAL", "Baltimore Ravens"),
            ("BUF", "Buffalo Bills"),
            ("CAR", "Carolina Panthers"),
            ("CHI", "Chicago Bears"),
            ("CIN", "Cincinnati Bengals"),
            ("CLE", "Cleveland Browns"),
            ("DAL", "Dallas Cowboys"),
            ("DEN", "Denver Broncos"),
            ("DET", "Detroit Lions"),
            ("GB", "Green Bay Packers"),
            ("HOU", "Houston Texans"),
            ("IND", "Indianapolis Colts"),
            ("JAX", "Jacksonville Jaguars", "JAC"),
            ("KC", "Kansas City Chiefs"),
            ("LV", "Las Vegas Raiders", "LVR"),
            ("LAC", "Los Angeles Chargers"),
            ("LAR", "Los Angeles Rams"),
            ("MIA", "Miami Dolphins"),
            ("MIN", "Minnesota Vikings"),
            ("NE", "New England Patriots"),
            ("NO", "New Orleans Saints"),
            ("NYG", "New York Giants"),
            ("NYJ", "New York Jets"),
            ("PHI", "Philadelphia Eagles"),
            ("PIT", "Pittsburgh Steelers"),
            ("SF", "San Francisco 49ers"),
            ("SEA", "Seattle Seahawks"),
            ("TB", "Tampa Bay Buccaneers"),
            ("TEN", "Tennessee Titans"),
            ("WSH", "Washington Commanders", "WAS"),
        ],
    ),
    "NBA": _team_logo_map(
        "nba",
        [
            ("ATL", "Atlanta Hawks"),
            ("BKN", "Brooklyn Nets", "BRK"),
            ("BOS", "Boston Celtics"),
            ("CHA", "Charlotte Hornets", "CHO"),
            ("CHI", "Chicago Bulls"),
            ("CLE", "Cleveland Cavaliers"),
            ("DAL", "Dallas Mavericks"),
            ("DEN", "Denver Nuggets"),
            ("DET", "Detroit Pistons"),
            ("GSW", "Golden State Warriors", "GS"),
            ("HOU", "Houston Rockets"),
            ("IND", "Indiana Pacers"),
            ("LAC", "LA Clippers"),
            ("LAL", "Los Angeles Lakers"),
            ("MEM", "Memphis Grizzlies"),
            ("MIA", "Miami Heat"),
            ("MIL", "Milwaukee Bucks"),
            ("MIN", "Minnesota Timberwolves"),
            ("NOP", "New Orleans Pelicans", "NO"),
            ("NYK", "New York Knicks"),
            ("OKC", "Oklahoma City Thunder"),
            ("ORL", "Orlando Magic"),
            ("PHI", "Philadelphia 76ers"),
            ("PHX", "Phoenix Suns", "PHO"),
            ("POR", "Portland Trail Blazers"),
            ("SAC", "Sacramento Kings"),
            ("SAS", "San Antonio Spurs", "SA"),
            ("TOR", "Toronto Raptors"),
            ("UTA", "Utah Jazz"),
            ("WSH", "Washington Wizards", "WAS"),
        ],
    ),
    # NL and AL stay as text. They are the All-Star Game, not clubs.
    # CHI is the Cubs wherever the sheet pairs it with CWS.
    "MLB": _team_logo_map(
        "mlb",
        [
            ("ARI", "Arizona Diamondbacks", "AZ"),
            ("ATH", "Athletics", "OAK"),
            ("ATL", "Atlanta Braves"),
            ("BAL", "Baltimore Orioles"),
            ("BOS", "Boston Red Sox"),
            ("CHC", "Chicago Cubs", "CHI"),
            ("CWS", "Chicago White Sox", "CHW"),
            ("CIN", "Cincinnati Reds"),
            ("CLE", "Cleveland Guardians"),
            ("COL", "Colorado Rockies"),
            ("DET", "Detroit Tigers"),
            ("HOU", "Houston Astros"),
            ("KC", "Kansas City Royals"),
            ("LAA", "Los Angeles Angels"),
            ("LAD", "Los Angeles Dodgers"),
            ("MIA", "Miami Marlins"),
            ("MIL", "Milwaukee Brewers"),
            ("MIN", "Minnesota Twins"),
            ("NYM", "New York Mets"),
            ("NYY", "New York Yankees"),
            ("PHI", "Philadelphia Phillies"),
            ("PIT", "Pittsburgh Pirates"),
            ("SD", "San Diego Padres", "SDP"),
            ("SF", "San Francisco Giants", "SFG"),
            ("SEA", "Seattle Mariners"),
            ("STL", "St. Louis Cardinals"),
            ("TB", "Tampa Bay Rays", "TBR"),
            ("TEX", "Texas Rangers"),
            ("TOR", "Toronto Blue Jays"),
            ("WSH", "Washington Nationals", "WAS"),
        ],
    ),
}


# ESPN serves a transparent PNG for each school at a stable id.
ESPN_NCAA_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png"


def _ncaa_logo_map(rows: List[Tuple[Tuple[str, ...], str, str]]) -> Dict[str, Tuple[str, str]]:
    mapping: Dict[str, Tuple[str, str]] = {}
    for abbrs, slug, name in rows:
        team_id = NCAA_ESPN_IDS.get(slug)
        ref = ESPN_NCAA_LOGO.format(team_id=team_id) if team_id and slug not in {"dayton", "utahTech"} else f"teams/ncaa/{slug.lower()}.png"
        for abbr in abbrs:
            mapping[abbr] = (ref, name)
    return mapping


# Abbreviations that clearly mean one school. Ambiguous codes are omitted
# so those picks stay as text.
NCAA_LOGO_TEAMS: List[Tuple[Tuple[str, ...], str, str]] = [
    (("DUKE", "DUK"), "duke", "Duke"),
    (("NCST",), "ncState", "NC State"),
    (("UNC",), "northCarolina", "North Carolina"),
    (("WAKE",), "wakeForest", "Wake Forest"),
    (("CLEM",), "clemson", "Clemson"),
    (("FSU",), "floridaState", "Florida State"),
    (("LOUI",), "louisville", "Louisville"),
    (("ND",), "notreDame", "Notre Dame"),
    (("SYR", "CUSE"), "syracuse", "Syracuse"),
    (("MIA", "MI-FL", "MIAMI"), "miami", "Miami"),
    (("MIOH", "MI-OH"), "miamiOH", "Miami (OH)"),
    (("STAN",), "stanford", "Stanford"),
    (("CAL",), "california", "California"),
    (("UCLA",), "ucla", "UCLA"),
    (("USC",), "usc", "USC"),
    (("WSU",), "washingtonState", "Washington State"),
    (("WASH",), "washington", "Washington"),
    (("ORE",), "oregon", "Oregon"),
    (("ORST",), "oregonState", "Oregon State"),
    (("ASU",), "arizonaState", "Arizona State"),
    (("ARIZ", "ARI"), "arizona", "Arizona"),
    (("COL", "COLO"), "colorado", "Colorado"),
    (("CSU",), "coloradoState", "Colorado State"),
    (("UTAH",), "utah", "Utah"),
    (("BYU",), "byu", "BYU"),
    (("BAY",), "baylor", "Baylor"),
    (("TCU",), "TCU", "TCU"),
    (("TTU",), "texasTech", "Texas Tech"),
    (("TEX",), "texas", "Texas"),
    (("OKST",), "OklahomaState", "Oklahoma State"),
    (("OKLA", "OU"), "oklahoma", "Oklahoma"),
    (("KSU",), "kansasState", "Kansas State"),
    (("KU", "KAN"), "kansas", "Kansas"),
    (("ISU",), "iowaState", "Iowa State"),
    (("HOU",), "houston", "Houston"),
    (("CIN",), "cincinnati", "Cincinnati"),
    (("UCF",), "ucf", "UCF"),
    (("WVU",), "westVirginia", "West Virginia"),
    (("IOWA", "IOW"), "iowa", "Iowa"),
    (("ILL",), "illinois", "Illinois"),
    (("IND", "IU"), "indiana", "Indiana"),
    (("INST", "INDS"), "indianaState", "Indiana State"),
    (("PUR",), "purdue", "Purdue"),
    (("MSU",), "michiganState", "Michigan State"),
    (("MICH",), "michigan", "Michigan"),
    (("OSU",), "ohioState", "Ohio State"),
    (("PSU",), "pennState", "Penn State"),
    (("WISC",), "wisconsin", "Wisconsin"),
    (("MINN",), "minnesota", "Minnesota"),
    (("NEB",), "nebraska", "Nebraska"),
    (("NW",), "northwestern", "Northwestern"),
    (("UMD", "MD"), "maryland", "Maryland"),
    (("RUT",), "rutgers", "Rutgers"),
    (("UK", "KY"), "kentucky", "Kentucky"),
    (("TEN", "TENN"), "tennessee", "Tennessee"),
    (("VAN", "VAND"), "vanderbilt", "Vanderbilt"),
    (("FLA",), "florida", "Florida"),
    (("UGA",), "georgia", "Georgia"),
    (("AUB",), "auburn", "Auburn"),
    (("BAMA", "ALA"), "alabama", "Alabama"),
    (("LSU",), "lsu", "LSU"),
    (("MISS",), "oleMiss", "Ole Miss"),
    (("MSST",), "mississippiState", "Mississippi State"),
    (("MIZZ", "MIZ"), "missouri", "Missouri"),
    (("ARK",), "arkansas", "Arkansas"),
    (("TAMU",), "texasAM", "Texas A&M"),
    (("SC",), "southCarolina", "South Carolina"),
    (("CONN",), "connecticut", "UConn"),
    (("BUT",), "butler", "Butler"),
    (("NOVA",), "villanova", "Villanova"),
    (("GTWN",), "georgetown", "Georgetown"),
    (("DAV", "DAVI"), "davidson", "Davidson"),
    (("DUQ",), "duquesne", "Duquesne"),
    (("URI",), "rhodeIsland", "Rhode Island"),
    (("MASS", "UMASS"), "massachusetts", "Massachusetts"),
    (("FOR",), "fordham", "Fordham"),
    (("SDSU",), "sanDiegoState", "San Diego State"),
    (("USD",), "sanDiego", "San Diego"),
    (("SD", "SDAK"), "southDakota", "South Dakota"),
    (("SDST",), "southDakotaState", "South Dakota State"),
    (("FRES",), "fresnoState", "Fresno State"),
    (("BSU",), "boiseState", "Boise State"),
    (("USU",), "utahState", "Utah State"),
    (("WYO",), "wyoming", "Wyoming"),
    (("UNLV",), "unlv", "UNLV"),
    (("NEV",), "nevada", "Nevada"),
    (("NM", "UNM"), "newMexico", "New Mexico"),
    (("NMSU", "NMST"), "newMexicoState", "New Mexico State"),
    (("SJSU",), "sanJoseState", "San Jose State"),
    (("AFA", "AF"), "airForce", "Air Force"),
    (("HAW",), "hawaii", "Hawaii"),
    (("UCD",), "ucDavis", "UC Davis"),
    (("CP", "SLO", "POLY"), "calPoly", "Cal Poly"),
    (("SAC", "SACR", "CSUS", "SAST"), "sacramentoState", "Sacramento State"),
    (("WEB",), "weberState", "Weber State"),
    (("NAU",), "northernArizona", "Northern Arizona"),
    (("EWU", "EW"), "easternWashington", "Eastern Washington"),
    (("IDA", "IDAH"), "idaho", "Idaho"),
    (("IDST",), "idahoState", "Idaho State"),
    (("MONT",), "montana", "Montana"),
    (("MNST", "MTST"), "montanaState", "Montana State"),
    (("UND",), "northDakota", "North Dakota"),
    (("NDSU", "NDST"), "northDakotaState", "North Dakota State"),
    (("NOCO",), "northernColorado", "Northern Colorado"),
    (("SUU",), "southernUtah", "Southern Utah"),
    (("ACU", "ABIL"), "abileneChristian", "Abilene Christian"),
    (("SHSU",), "samHoustonState", "Sam Houston"),
    (("KENN",), "kennesawState", "Kennesaw State"),
    (("PEAY",), "austinPeay", "Austin Peay"),
    (("LAM",), "lamar", "Lamar"),
    (("MCNS",), "mcNeeseState", "McNeese"),
    (("NICH",), "nichollsState", "Nicholls"),
    (("SFA",), "stephenFAustin", "Stephen F. Austin"),
    (("SELA", "SELO"), "southeasternLouisiana", "SE Louisiana"),
    (("SEM", "SEMO"), "southeastMissouriState", "Southeast Missouri"),
    (("UCA",), "centralArkansas", "Central Arkansas"),
    (("TUL", "TULN"), "tulane", "Tulane"),
    (("TLSA", "TULS"), "tulsa", "Tulsa"),
    (("MEM",), "memphis", "Memphis"),
    (("SMU",), "smu", "SMU"),
    (("UTSA",), "texasSanAntonio", "UTSA"),
    (("UTEP",), "utep", "UTEP"),
    (("UNT",), "northTexas", "North Texas"),
    (("TXST",), "texasState", "Texas State"),
    (("TXSO",), "texasSouthern", "Texas Southern"),
    (("LT",), "LouisianaTech", "Louisiana Tech"),
    (("WKY",), "westernKentucky", "Western Kentucky"),
    (("MTSU",), "middleTennessee", "Middle Tennessee"),
    (("FIU",), "floridaIntl", "FIU"),
    (("FAU",), "floridaAtlantic", "FAU"),
    (("USF",), "southFlorida", "South Florida"),
    (("CHAR",), "charlotte", "Charlotte"),
    (("APP", "APST"), "appalachianState", "Appalachian State"),
    (("UAB",), "uab", "UAB"),
    (("MRSH", "MAR"), "marshall", "Marshall"),
    (("LIB",), "liberty", "Liberty"),
    (("TEM", "TEMP"), "temple", "Temple"),
    (("TOL",), "toledo", "Toledo"),
    (("BG", "BGSU"), "bowlingGreen", "Bowling Green"),
    (("CMU",), "centralMichigan", "Central Michigan"),
    (("EMU",), "easternMichigan", "Eastern Michigan"),
    (("WMU",), "westernMichigan", "Western Michigan"),
    (("KENT",), "kentState", "Kent State"),
    (("AKR",), "akron", "Akron"),
    (("OHIO",), "ohio", "Ohio"),
    (("BUF", "BUFF"), "buffalo", "Buffalo"),
    (("BALL",), "ballState", "Ball State"),
    (("NIU",), "northernIllinois", "Northern Illinois"),
    (("MOST",), "missouriState", "Missouri State"),
    (("DRAK",), "drake", "Drake"),
    (("UNI",), "northernIowa", "Northern Iowa"),
    (("ILST",), "illinoisState", "Illinois State"),
    (("VALP", "VAL"), "valparaiso", "Valparaiso"),
    (("MURR",), "murrayState", "Murray State"),
    (("EIU",), "easternIllinois", "Eastern Illinois"),
    (("TNST",), "tennesseeState", "Tennessee State"),
    (("TNTC",), "tennesseeTech", "Tennessee Tech"),
    (("UTM",), "tennesseeMartin", "UT Martin"),
    (("EKU", "EKY"), "easternKentucky", "Eastern Kentucky"),
    (("JVST", "JXST"), "jacksonvilleState", "Jacksonville State"),
    (("JSU", "JKST"), "jacksonState", "Jackson State"),
    (("JAX",), "jacksonville", "Jacksonville"),
    (("BCU",), "bethuneCookman", "Bethune-Cookman"),
    (("AAMU",), "alabamaAM", "Alabama A&M"),
    (("ALST",), "alabamaState", "Alabama State"),
    (("GRAM",), "gramblingState", "Grambling"),
    (("PVAM",), "prairieView", "Prairie View"),
    (("NCAT",), "northCarolinaAT", "NC A&T"),
    (("NCC",), "northCarolinaCentral", "NC Central"),
    (("HOW",), "howard", "Howard"),
    (("SCST",), "southCarolinaState", "South Carolina State"),
    (("MORG",), "morganState", "Morgan State"),
    (("UL",), "louisianaLafayette", "Louisiana"),
    (("ULM",), "louisianaMonroe", "UL Monroe"),
    (("TROY",), "troy", "Troy"),
    (("USA",), "southAlabama", "South Alabama"),
    (("GASO",), "georgiaSouthern", "Georgia Southern"),
    (("GAST",), "georgiaState", "Georgia State"),
    (("CCU",), "coastalCarolina", "Coastal Carolina"),
    (("ARST",), "arkansasState", "Arkansas State"),
    (("WIU",), "westernIllinois", "Western Illinois"),
    (("YSU",), "youngstownState", "Youngstown State"),
    (("PRST",), "portlandState", "Portland State"),
    (("ECU",), "eastCarolina", "East Carolina"),
    (("USM",), "southernMississippi", "Southern Miss"),
    (("BRY",), "bryant", "Bryant"),
    (("APB",), "arkansasPineBluff", "Arkansas-Pine Bluff"),
    (("SFPA",), "stFrancisPA", "St. Francis (PA)"),
    (("STET",), "stetson", "Stetson"),
    (("MVSU",), "mississippiValleyState", "Mississippi Valley State"),
    (("MON", "MONM"), "monmouth", "Monmouth"),
    (("CHSO",), "charlestonSouthern", "Charleston Southern"),
    (("CHAT", "UTC"), "chattanooga", "Chattanooga"),
    (("WOF", "WOFF"), "wofford", "Wofford"),
    (("ETSU",), "eastTennessee", "ETSU"),
    (("FUR",), "furman", "Furman"),
    (("SAM",), "samford", "Samford"),
    (("WC", "WCU"), "westernCarolina", "Western Carolina"),
    (("MER", "MERC"), "mercer", "Mercer"),
    (("CIT",), "citadel", "The Citadel"),
    (("ELON",), "elon", "Elon"),
    (("DEL",), "delaware", "Delaware"),
    (("DSU",), "delawareState", "Delaware State"),
    (("TOW", "TOWS"), "towson", "Towson"),
    (("UNH",), "newHampshire", "New Hampshire"),
    (("ME",), "maine", "Maine"),
    (("ALB",), "albany", "Albany"),
    (("HARV",), "harvard", "Harvard"),
    (("YALE", "YAL"), "yale", "Yale"),
    (("PRIN",), "princeton", "Princeton"),
    (("PENN",), "penn", "Penn"),
    (("COR", "CORN"), "cornell", "Cornell"),
    (("DART",), "dartmouth", "Dartmouth"),
    (("HC",), "holyCross", "Holy Cross"),
    (("LEH",), "lehigh", "Lehigh"),
    (("LAF",), "lafayette", "Lafayette"),
    (("BUC",), "bucknell", "Bucknell"),
    (("NAVY",), "navy", "Navy"),
    (("ARMY",), "army", "Army"),
    (("SBK", "STBK"), "stonyBrook", "Stony Brook"),
    (("BU",), "boston", "Boston University"),
    (("GT",), "georgiaTech", "Georgia Tech"),
    (("PIT", "PITT"), "pittsburgh", "Pittsburgh"),
    (("RICE",), "rice", "Rice"),
    (("MORE",), "moreheadState", "Morehead State"),
    (("MARS",), "marist", "Marist"),
    (("WIL",), "williamMary", "William & Mary"),
    (("WAG",), "wagner", "Wagner"),
    (("RM", "RMU"), "robertMorris", "Robert Morris"),
    (("PRES", "PRE"), "presbyterianCollege", "Presbyterian"),
    (("CB", "CBU"), "californiaBaptist", "California Baptist"),
]

NCAAF_ONLY_LOGO_TEAMS: List[Tuple[Tuple[str, ...], str, str]] = [
    (("SHU",), "sacredHeart", "Sacred Heart"),
]

# Schools missing from the original NCAA pack. Marks are the sdv-assets default PNGs.
NCAA_GAP_LOGO_TEAMS: List[Tuple[Tuple[str, ...], str, str]] = [
    (("DAY",), "dayton", "Dayton"),
    (("UTU",), "utahTech", "Utah Tech"),
    (("SJU",), "stJohns", "St. John's"),
    (("GONZ", "ZAGA"), "gonzaga", "Gonzaga"),
    (("BEL", "BELM"), "belmont", "Belmont"),
    (("MARQ",), "marquette", "Marquette"),
    (("BC",), "bostonCollege", "Boston College"),
    (("CLAR", "SCU"), "santaClara", "Santa Clara"),
    (("CSF", "CSUF"), "calStateFullerton", "Cal State Fullerton"),
    (("PROV",), "providence", "Providence"),
    (("LAS", "LASL"), "laSalle", "La Salle"),
    (("SET",), "setonHall", "Seton Hall"),
    (("XAV",), "xavier", "Xavier"),
    (("CREI",), "creighton", "Creighton"),
    (("DEP",), "depaul", "DePaul"),
    (("SMC",), "saintMarys", "Saint Mary's"),
    (("GCU",), "grandCanyon", "Grand Canyon"),
    (("UCSB",), "ucSantaBarbara", "UC Santa Barbara"),
    (("SEA",), "seattleU", "Seattle"),
    (("HOF",), "hofstra", "Hofstra"),
    (("SF",), "sanFrancisco", "San Francisco"),
    (("SLU",), "saintLouis", "Saint Louis"),
    (("UCSD",), "ucSanDiego", "UC San Diego"),
    (("EVAN",), "evansville", "Evansville"),
    (("SIEN",), "siena", "Siena"),
    (("UCI",), "ucIrvine", "UC Irvine"),
    (("DREX",), "drexel", "Drexel"),
    (("UNCG",), "uncGreensboro", "UNC Greensboro"),
    (("WICH",), "wichitaState", "Wichita State"),
    (("LIND",), "lindenwood", "Lindenwood"),
    (("BRAD",), "bradley", "Bradley"),
    (("PORT",), "portland", "Portland"),
    (("IONA",), "iona", "Iona"),
    (("PEPP",), "pepperdine", "Pepperdine"),
    (("LMU",), "loyolaMarymount", "Loyola Marymount"),
    (("BON", "BONA"), "stBonaventure", "St. Bonaventure"),
    (("MSM",), "mountStMarys", "Mount St. Mary's"),
    (("FAIR",), "fairfield", "Fairfield"),
    (("UTA",), "utArlington", "UT Arlington"),
    (("IPFW",), "purdueFortWayne", "Purdue Fort Wayne"),
    (("GB",), "greenBay", "Green Bay"),
    (("DEN",), "denver", "Denver"),
    (("CSUB",), "calStateBakersfield", "Cal State Bakersfield"),
    (("JOES",), "saintJosephs", "Saint Joseph's"),
    (("UVU",), "utahValley", "Utah Valley"),
    (("NE",), "northeastern", "Northeastern"),
    (("COFC",), "charleston", "Charleston"),
    (("MERR", "MRMK"), "merrimack", "Merrimack"),
    (("GW",), "georgeWashington", "George Washington"),
    (("NIA",), "niagara", "Niagara"),
    (("CANS",), "canisius", "Canisius"),
    (("UIC", "ILC"), "uic", "UIC"),
    (("LOY", "LOYC"), "loyolaChicago", "Loyola Chicago"),
    (("AMER",), "american", "American"),
    (("UNCW",), "uncWilmington", "UNC Wilmington"),
    (("TRGV",), "utRioGrandeValley", "UT Rio Grande Valley"),
    (("BELL",), "bellarmine", "Bellarmine"),
    (("CLE", "CLST"), "clevelandState", "Cleveland State"),
    (("QUIN",), "quinnipiac", "Quinnipiac"),
    (("ORU",), "oralRoberts", "Oral Roberts"),
    (("UMKC",), "kansasCity", "Kansas City"),
    (("PAC",), "pacific", "Pacific"),
    (("UCR",), "ucRiverside", "UC Riverside"),
    (("OAK",), "oakland", "Oakland"),
    (("SOU",), "southern", "Southern"),
    (("LBSU",), "longBeachState", "Long Beach State"),
    (("HPU",), "highPoint", "High Point"),
    (("LIPS",), "lipscomb", "Lipscomb"),
    (("UNCA",), "uncAsheville", "UNC Asheville"),
    (("MILW",), "milwaukee", "Milwaukee"),
    (("NJIT",), "njit", "NJIT"),
    (("FGCU",), "floridaGulfCoast", "Florida Gulf Coast"),
    (("DET",), "detroitMercy", "Detroit Mercy"),
    (("SIUE",), "siuEdwardsville", "SIU Edwardsville"),
    (("MANH",), "manhattan", "Manhattan"),
    (("ETAM",), "eastTexasAM", "East Texas A&M"),
    (("USI",), "southernIndiana", "Southern Indiana"),
    (("PETE",), "saintPeters", "Saint Peter's"),
    (("TAR", "TARL"), "tarletonState", "Tarleton State"),
    (("OMA", "OMAH"), "omaha", "Omaha"),
    (("THOM", "UST"), "stThomas", "St. Thomas"),
    (("WIN",), "winthrop", "Winthrop"),
    (("UMBC",), "umbc", "UMBC"),
    (("LR",), "littleRock", "Little Rock"),
    (("NKY",), "northernKentucky", "Northern Kentucky"),
    (("UML",), "umassLowell", "UMass Lowell"),
    (("AMCC",), "texasAMCorpusChristi", "Texas A&M-Corpus Christi"),
    (("QUC",), "quincy", "Quincy"),
    (("LIU",), "longIsland", "Long Island"),
    (("UNA",), "northAlabama", "North Alabama"),
]

# ESPN team ids for the schools above. Cards load
# https://a.espncdn.com/i/teamlogos/ncaa/500/{id}.png
NCAA_ESPN_IDS: Dict[str, str] = {
    "dayton": "2168",
    "utahTech": "3101",
    "LouisianaTech": "2348",
    "OklahomaState": "197",
    "TCU": "2628",
    "abileneChristian": "2000",
    "airForce": "2005",
    "akron": "2006",
    "alabama": "333",
    "alabamaAM": "2010",
    "alabamaState": "2011",
    "albany": "399",
    "american": "44",
    "appalachianState": "2026",
    "arizona": "12",
    "arizonaState": "9",
    "arkansas": "8",
    "arkansasPineBluff": "2029",
    "arkansasState": "2032",
    "army": "349",
    "auburn": "2",
    "austinPeay": "2046",
    "ballState": "2050",
    "baylor": "239",
    "bellarmine": "91",
    "belmont": "2057",
    "bethuneCookman": "2065",
    "boiseState": "68",
    "boston": "104",
    "bostonCollege": "103",
    "bowlingGreen": "189",
    "bradley": "71",
    "bryant": "2803",
    "bucknell": "2083",
    "buffalo": "2084",
    "butler": "2086",
    "byu": "252",
    "calPoly": "13",
    "calStateBakersfield": "2934",
    "calStateFullerton": "2239",
    "california": "25",
    "californiaBaptist": "2856",
    "canisius": "2099",
    "centralArkansas": "2110",
    "centralMichigan": "2117",
    "charleston": "232",
    "charlestonSouthern": "2127",
    "charlotte": "2429",
    "chattanooga": "236",
    "cincinnati": "2132",
    "citadel": "2643",
    "clemson": "228",
    "clevelandState": "325",
    "coastalCarolina": "324",
    "colorado": "38",
    "coloradoState": "36",
    "connecticut": "41",
    "cornell": "172",
    "creighton": "156",
    "dartmouth": "159",
    "davidson": "2166",
    "delaware": "48",
    "delawareState": "2169",
    "denver": "2172",
    "depaul": "305",
    "detroitMercy": "2174",
    "drake": "2181",
    "drexel": "2182",
    "duke": "150",
    "duquesne": "2184",
    "eastCarolina": "151",
    "eastTennessee": "2193",
    "eastTexasAM": "2837",
    "easternIllinois": "2197",
    "easternKentucky": "2198",
    "easternMichigan": "2199",
    "easternWashington": "331",
    "elon": "2210",
    "evansville": "339",
    "fairfield": "2217",
    "florida": "57",
    "floridaAtlantic": "2226",
    "floridaGulfCoast": "526",
    "floridaIntl": "2229",
    "floridaState": "52",
    "fordham": "2230",
    "fresnoState": "278",
    "furman": "231",
    "georgeWashington": "45",
    "georgetown": "46",
    "georgia": "61",
    "georgiaSouthern": "290",
    "georgiaState": "2247",
    "georgiaTech": "59",
    "gonzaga": "2250",
    "gramblingState": "2755",
    "grandCanyon": "2253",
    "greenBay": "2739",
    "harvard": "108",
    "hawaii": "62",
    "highPoint": "2272",
    "hofstra": "2275",
    "holyCross": "107",
    "houston": "248",
    "howard": "47",
    "idaho": "70",
    "idahoState": "304",
    "illinois": "356",
    "illinoisState": "2287",
    "indiana": "84",
    "indianaState": "282",
    "iona": "314",
    "iowa": "2294",
    "iowaState": "66",
    "jacksonState": "2296",
    "jacksonville": "294",
    "jacksonvilleState": "55",
    "kansas": "2305",
    "kansasCity": "140",
    "kansasState": "2306",
    "kennesawState": "338",
    "kentState": "2309",
    "kentucky": "96",
    "laSalle": "2325",
    "lafayette": "322",
    "lamar": "2320",
    "lehigh": "2329",
    "liberty": "2335",
    "lindenwood": "2815",
    "lipscomb": "288",
    "littleRock": "2031",
    "longBeachState": "299",
    "longIsland": "112358",
    "louisianaLafayette": "309",
    "louisianaMonroe": "2433",
    "louisville": "97",
    "loyolaChicago": "2350",
    "loyolaMarymount": "2351",
    "lsu": "99",
    "maine": "311",
    "manhattan": "2363",
    "marist": "2368",
    "marquette": "269",
    "marshall": "276",
    "maryland": "120",
    "massachusetts": "113",
    "mcNeeseState": "2377",
    "memphis": "235",
    "mercer": "2382",
    "merrimack": "2771",
    "miami": "2390",
    "miamiOH": "193",
    "michigan": "130",
    "michiganState": "127",
    "middleTennessee": "2393",
    "milwaukee": "270",
    "minnesota": "135",
    "mississippiState": "344",
    "mississippiValleyState": "2400",
    "missouri": "142",
    "missouriState": "2623",
    "monmouth": "2405",
    "montana": "149",
    "montanaState": "147",
    "moreheadState": "2413",
    "morganState": "2415",
    "mountStMarys": "116",
    "murrayState": "93",
    "navy": "2426",
    "ncState": "152",
    "nebraska": "158",
    "nevada": "2440",
    "newHampshire": "160",
    "newMexico": "167",
    "newMexicoState": "166",
    "niagara": "315",
    "nichollsState": "2447",
    "njit": "2885",
    "northAlabama": "2453",
    "northCarolina": "153",
    "northCarolinaAT": "2448",
    "northCarolinaCentral": "2428",
    "northDakota": "155",
    "northDakotaState": "2449",
    "northTexas": "249",
    "northeastern": "111",
    "northernArizona": "2464",
    "northernColorado": "2458",
    "northernIllinois": "2459",
    "northernIowa": "2460",
    "northernKentucky": "94",
    "northwestern": "77",
    "notreDame": "87",
    "oakland": "2473",
    "ohio": "195",
    "ohioState": "194",
    "oklahoma": "201",
    "oleMiss": "145",
    "omaha": "2437",
    "oralRoberts": "198",
    "oregon": "2483",
    "oregonState": "204",
    "pacific": "279",
    "penn": "219",
    "pennState": "213",
    "pepperdine": "2492",
    "pittsburgh": "221",
    "portland": "2501",
    "portlandState": "2502",
    "prairieView": "2504",
    "presbyterianCollege": "2506",
    "princeton": "163",
    "providence": "2507",
    "purdue": "2509",
    "purdueFortWayne": "2870",
    "quincy": "2825",
    "quinnipiac": "2514",
    "rhodeIsland": "227",
    "rice": "242",
    "robertMorris": "2523",
    "rutgers": "164",
    "sacramentoState": "16",
    "sacredHeart": "2529",
    "saintJosephs": "2603",
    "saintLouis": "139",
    "saintMarys": "2608",
    "saintPeters": "2612",
    "samHoustonState": "2534",
    "samford": "2535",
    "sanDiego": "301",
    "sanDiegoState": "21",
    "sanFrancisco": "2539",
    "sanJoseState": "23",
    "santaClara": "2541",
    "seattleU": "2547",
    "setonHall": "2550",
    "siena": "2561",
    "siuEdwardsville": "2565",
    "smu": "2567",
    "southAlabama": "6",
    "southCarolina": "2579",
    "southCarolinaState": "2569",
    "southDakota": "233",
    "southDakotaState": "2571",
    "southFlorida": "58",
    "southeastMissouriState": "2546",
    "southeasternLouisiana": "2545",
    "southern": "2582",
    "southernIndiana": "88",
    "southernMississippi": "2572",
    "southernUtah": "253",
    "stBonaventure": "179",
    "stFrancisPA": "2598",
    "stJohns": "2599",
    "stThomas": "2900",
    "stanford": "24",
    "stephenFAustin": "2617",
    "stetson": "56",
    "stonyBrook": "2619",
    "syracuse": "183",
    "tarletonState": "2627",
    "temple": "218",
    "tennessee": "2633",
    "tennesseeMartin": "2630",
    "tennesseeState": "2634",
    "tennesseeTech": "2635",
    "texas": "251",
    "texasAM": "245",
    "texasAMCorpusChristi": "357",
    "texasSanAntonio": "2636",
    "texasSouthern": "2640",
    "texasState": "326",
    "texasTech": "2641",
    "toledo": "2649",
    "towson": "119",
    "troy": "2653",
    "tulane": "2655",
    "tulsa": "202",
    "uab": "5",
    "ucDavis": "302",
    "ucIrvine": "300",
    "ucRiverside": "27",
    "ucSanDiego": "28",
    "ucSantaBarbara": "2540",
    "ucf": "2116",
    "ucla": "26",
    "uic": "82",
    "umassLowell": "2349",
    "umbc": "2378",
    "uncAsheville": "2427",
    "uncGreensboro": "2430",
    "uncWilmington": "350",
    "unlv": "2439",
    "usc": "30",
    "utArlington": "250",
    "utRioGrandeValley": "292",
    "utah": "254",
    "utahState": "328",
    "utahValley": "3084",
    "utep": "2638",
    "valparaiso": "2674",
    "vanderbilt": "238",
    "villanova": "222",
    "wagner": "2681",
    "wakeForest": "154",
    "washington": "264",
    "washingtonState": "265",
    "weberState": "2692",
    "westVirginia": "277",
    "westernCarolina": "2717",
    "westernIllinois": "2710",
    "westernKentucky": "98",
    "westernMichigan": "2711",
    "wichitaState": "2724",
    "williamMary": "2729",
    "winthrop": "2737",
    "wisconsin": "275",
    "wofford": "2747",
    "wyoming": "2751",
    "xavier": "2752",
    "yale": "43",
    "youngstownState": "2754",
}

TEAM_LOGO_BY_LEAGUE["NCAAB"] = _ncaa_logo_map(NCAA_LOGO_TEAMS + NCAA_GAP_LOGO_TEAMS)
TEAM_LOGO_BY_LEAGUE["NCAAF"] = _ncaa_logo_map(
    NCAA_LOGO_TEAMS + NCAAF_ONLY_LOGO_TEAMS + NCAA_GAP_LOGO_TEAMS
)

_TEAM_ABBR_RE = re.compile(r"\b([A-Z]{2,6}(?:-[A-Z]{2,4})?)\b")


BADGE_FALLBACK_PALETTE = [
    "#38BDF8",
    "#22C55E",
    "#F59E0B",
    "#EF4444",
    "#A78BFA",
    "#14B8A6",
    "#F97316",
    "#84CC16",
    "#06B6D4",
    "#E879F9",
]


def _normalize_key(label: str) -> str:
    return "".join(ch for ch in (label or "").upper() if ch.isalnum())


def _fallback_color(label: str) -> str:
    key = _normalize_key(label)
    if not key:
        return "#64748B"
    return BADGE_FALLBACK_PALETTE[sum(ord(ch) for ch in key) % len(BADGE_FALLBACK_PALETTE)]


def _text_color_for_bg(hex_color: str) -> str:
    s = (hex_color or "").lstrip("#")
    if len(s) != 6:
        return "#F8FAFC"
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#0B1220" if luminance > 0.62 else "#F8FAFC"


def _join_href(base: str, filename: str) -> str:
    b = (base or "").strip().rstrip("/")
    f = (filename or "").strip().lstrip("/")
    if not b:
        return f
    return f"{b}/{f}"


def _logo_href(
    label: str,
    logo_map: Dict[str, str],
    logo_base_href: str,
    available_logo_files: Optional[set[str]],
) -> Optional[str]:
    filename = logo_map.get(_normalize_key(label))
    if not filename:
        return None
    if available_logo_files is not None and filename.lower() not in available_logo_files:
        return None
    return _join_href(logo_base_href, filename)


def _badge_html(label: str, color: str, logo_href: Optional[str] = None) -> str:
    safe = html.escape((label or "").strip() or "(blank)")
    if logo_href:
        safe_logo_href = html.escape(logo_href, quote=True)
        return (
            '<span class="badge badge-logo" title="'
            f'{safe}">'
            f'<img class="badge-logo-img" src="{safe_logo_href}" alt="{safe}" loading="lazy" decoding="async" />'
            "</span>"
        )
    fg = _text_color_for_bg(color)
    return (
        f'<span class="badge badge-sticker" style="background:{color}; border-color:{color}; color:{fg};">{safe}</span>'
    )


def _league_badge(
    league: str, logo_base_href: str = "logos", available_logo_files: Optional[set[str]] = None
) -> str:
    key = _normalize_key(league)
    color = LEAGUE_COLOR_MAP.get(key, _fallback_color(league))
    logo_href = _logo_href(league, LEAGUE_LOGO_MAP, logo_base_href, available_logo_files)
    return _badge_html(league, color, logo_href=logo_href)


def _book_badge(
    book: str, logo_base_href: str = "logos", available_logo_files: Optional[set[str]] = None
) -> str:
    key = _normalize_key(book)
    color = BOOK_COLOR_MAP.get(key, _fallback_color(book))
    logo_href = _logo_href(book, BOOK_LOGO_MAP, logo_base_href, available_logo_files)
    return _badge_html(book, color, logo_href=logo_href)


def _team_logo_for_abbr(
    abbr: str,
    league: str,
    available_logo_files: Optional[set[str]] = None,
) -> Optional[Tuple[str, str]]:
    """Return (filename, full name) when this abbreviation is shown as a logo."""
    mapping = TEAM_LOGO_BY_LEAGUE.get((league or "").strip().upper())
    if not mapping:
        return None
    entry = mapping.get(abbr)
    if entry is None:
        return None
    filename, name = entry
    remote = filename.startswith("http://") or filename.startswith("https://")
    if not remote and available_logo_files is not None and filename.lower() not in available_logo_files:
        return None
    return filename, name


def _display_pick(pick: str) -> str:
    """Remove sheet separators while preserving names like Texas A&M and fractions."""
    return re.sub(r"\s+", " ", re.sub(r"(?<!\d)/(?!\d)|(?<!\w)&(?!\w)|(?<!\d),|,(?!\d)", " ", pick)).strip()


def _parlay_leg_count(pick: str) -> Optional[int]:
    """Count listed legs without splitting matchups, fractions, or combined stats."""
    explicit = re.search(r"\b(\d+)[ -]+leg(?:s)?\b", pick, re.IGNORECASE)
    if explicit:
        return int(explicit.group(1))
    stats = r"(?:pts|points|reb|rebounds|ast|assists)"
    counted = re.sub(rf"\b({stats})\s+(?:&|and)\s+(?={stats}\b)", r"\1 + ", pick, flags=re.IGNORECASE)
    parts = [part.strip() for part in re.split(r"(?<!\d),|,(?!\d)|(?<!\w)&(?!\w)|\band\b|;", counted, flags=re.IGNORECASE) if part.strip()]
    return len(parts) if len(parts) > 1 else None


def _today_pick_text(
    pick: str,
    league: str,
    available_logo_files: Optional[set[str]] = None,
) -> str:
    """Pick text with shown logos expanded to full team names."""
    def replace(match: re.Match[str]) -> str:
        logo = _team_logo_for_abbr(match.group(1), league, available_logo_files)
        return logo[1] if logo else match.group(1)

    return _TEAM_ABBR_RE.sub(replace, _display_pick(pick))


def _today_pick_html(
    pick: str,
    league: str,
    logo_base_href: str = "logos",
    available_logo_files: Optional[set[str]] = None,
) -> str:
    """Replace team abbreviations on today cards with a uniform logo."""
    pick = _display_pick(pick)
    parts: List[str] = []
    last = 0
    for match in _TEAM_ABBR_RE.finditer(pick):
        parts.append(html.escape(pick[last:match.start()]))
        abbr = match.group(1)
        logo = _team_logo_for_abbr(abbr, league, available_logo_files)
        if logo is None:
            parts.append(html.escape(abbr))
        else:
            filename, name = logo
            if filename.startswith("http://") or filename.startswith("https://"):
                href = html.escape(filename, quote=True)
            else:
                href = html.escape(_join_href(logo_base_href, filename), quote=True)
            label = html.escape(name, quote=True)
            parts.append(
                f'<span class="team-logo-tip" data-name="{label}">'
                f'<img class="team-logo" src="{href}" alt="{label}" '
                'loading="lazy" decoding="async" /></span>'
            )
        last = match.end()
    parts.append(html.escape(pick[last:]))
    return "".join(parts)


# Scoreboard join. College cards already use the ESPN team id in the logo URL,
# and that same id is on the scoreboard. Pro logos are local files, so those
# match on ESPN's abbreviation. The overrides are the canonical file stems
# that ESPN spells differently (LAK is LA, CWS is CHW, UTA is UTAH).
_ESPN_ABBR_OVERRIDE = {
    ("NHL", "LAK"): "LA",
    ("NHL", "NJD"): "NJ",
    ("NHL", "SJS"): "SJ",
    ("NHL", "TBL"): "TB",
    # The NHL scoreboard spells Utah as UTA. The teams list says UTAH, and the
    # NBA scoreboard really does use UTAH, so only basketball is overridden.
    ("NBA", "GSW"): "GS",
    ("NBA", "NOP"): "NO",
    ("NBA", "NYK"): "NY",
    ("NBA", "SAS"): "SA",
    ("NBA", "UTA"): "UTAH",
    ("MLB", "CWS"): "CHW",
}
_ESPN_SCOREBOARDS = {
    "NHL": ("hockey/nhl", ("",)),
    "NFL": ("football/nfl", ("",)),
    "NBA": ("basketball/nba", ("",)),
    "MLB": ("baseball/mlb", ("",)),
    # Empty group is the default board (FBS). 81 is FCS.
    "NCAAF": ("football/college-football", ("", "81")),
    # Group 50 is Division I. The default board is only a handful of games.
    "NCAAB": ("basketball/mens-college-basketball", ("50",)),
}
_ESPN_TEAM_ID_RE = re.compile(r"/ncaa/500/(\d+)\.png$", re.IGNORECASE)
_MATCHUP_RE = re.compile(r"\b([A-Z]{2,6}(?:-[A-Z]{2,4})?)/([A-Z]{2,6}(?:-[A-Z]{2,4})?)\b")
_EASTERN = ZoneInfo("America/New_York")


def _team_ref(abbr: str, league: str) -> Optional[Dict[str, str]]:
    """Sheet abbreviation -> name, ESPN abbreviation, and ESPN team id when we have one."""
    league = (league or "").strip().upper()
    mapping = TEAM_LOGO_BY_LEAGUE.get(league)
    if not mapping:
        return None
    entry = mapping.get(abbr)
    if entry is None:
        return None
    filename, name = entry
    id_match = _ESPN_TEAM_ID_RE.search(filename)
    espn_id = id_match.group(1) if id_match else ""
    if not espn_id and league in {"NCAAB", "NCAAF"}:
        local_slug = os.path.splitext(os.path.basename(filename))[0].casefold()
        espn_id = next((team_id for slug, team_id in NCAA_ESPN_IDS.items() if slug.casefold() == local_slug), "")
    if filename.startswith("teams/"):
        canonical = os.path.splitext(os.path.basename(filename))[0].upper()
    else:
        canonical = abbr
    return {
        "abbr": abbr,
        "name": name,
        "espn_abbr": _ESPN_ABBR_OVERRIDE.get((league, canonical), canonical),
        "espn_id": espn_id,
    }


def _recognized_teams(pick: str, league: str) -> List[Dict[str, str]]:
    seen = set()
    teams = []
    for abbr in _TEAM_ABBR_RE.findall(pick or ""):
        ref = _team_ref(abbr, league)
        if ref is None:
            continue
        key = ref["espn_id"] or ref["espn_abbr"]
        if key in seen:
            continue
        seen.add(key)
        teams.append(ref)
    return teams


def _matchup_from_pick(
    pick: str, league: str
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Teams to look up: both sides of one A/B matchup, or the one named team."""
    league = (league or "").strip().upper()
    pairs: List[Tuple[Dict[str, str], Dict[str, str]]] = []
    seen = set()
    partial: List[str] = []
    missing_ids: List[str] = []
    for left, right in _MATCHUP_RE.findall(pick or ""):
        away = _team_ref(left, league)
        home = _team_ref(right, league)
        if away and home:
            if league in {"NCAAB", "NCAAF"} and not (away["espn_id"] and home["espn_id"]):
                missing_ids.append(away["abbr"] if not away["espn_id"] else home["abbr"])
                continue
            key = tuple(
                sorted(
                    (
                        away["espn_id"] or away["espn_abbr"],
                        home["espn_id"] or home["espn_abbr"],
                    )
                )
            )
            if key not in seen:
                seen.add(key)
                pairs.append((away, home))
        elif away or home:
            partial.append(left if away is None else right)
    if len(pairs) == 1:
        return list(pairs[0]), None
    if len(pairs) > 1:
        return [], "pick names more than one matchup"
    if missing_ids:
        return [], f"no ESPN team id for {missing_ids[0]}"
    if partial:
        return [], f"unrecognized team ({partial[0]})"
    teams = _recognized_teams(pick, league)
    if not teams:
        return [], "no recognized team abbreviation"
    if len(teams) == 1:
        team = teams[0]
        if league in {"NCAAB", "NCAAF"} and not team["espn_id"]:
            return [], f"no ESPN team id for {team['abbr']}"
        return [team], None
    names = ", ".join(team["name"] for team in teams)
    return [], f"teams are not written as one matchup ({names})"


def _matching_games(games: List[Dict[str, Any]], teams: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    if all(team.get("espn_id") for team in teams):
        wanted = {team["espn_id"] for team in teams}
        return [game for game in games if wanted <= game["ids"]]
    wanted = {team["espn_abbr"] for team in teams}
    return [game for game in games if wanted <= game["abbrs"]]


def _format_game_start(raw: str) -> Optional[Tuple[str, str]]:
    text = (raw or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if not text:
        return None
    try:
        start = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    eastern = start.astimezone(_EASTERN)
    hour = eastern.strftime("%I").lstrip("0")
    clock = f"{hour}:{eastern.minute:02d}" if eastern.minute else hour
    return f"{clock} {eastern.strftime('%p')}", start.isoformat()


def _game_from_espn_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    abbrs: List[str] = []
    ids: List[str] = []
    home = ""
    away = ""
    sides: Dict[str, Dict[str, Any]] = {}
    for competitor in comp.get("competitors") or []:
        team = competitor.get("team") or {}
        abbr = str(team.get("abbreviation") or "").upper()
        team_id = str(team.get("id") or "")
        if abbr:
            abbrs.append(abbr)
        if team_id:
            ids.append(team_id)
        name = str(team.get("displayName") or abbr)
        side = competitor.get("homeAway")
        if side in {"home", "away"}:
            sides[side] = {
                "id": team_id,
                "abbr": abbr,
                "name": name,
                "score": str(competitor["score"]) if competitor.get("score") is not None else None,
            }
        if side == "home":
            home = name
        elif side == "away":
            away = name
    if len(abbrs) < 2 and len(ids) < 2:
        return None
    formatted = _format_game_start(str(event.get("date") or comp.get("date") or ""))
    if formatted is None:
        return None
    display, iso = formatted
    status = comp.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    done = bool(status_type.get("completed")) or status_type.get("state") == "post"
    if away and home:
        matchup = f"{away} vs {home}" if comp.get("neutralSite") else f"{away} at {home}"
    else:
        matchup = str(event.get("shortName") or "")
    venue = comp.get("venue") or {}
    venue_name = str(venue.get("fullName") or "")
    city = str((venue.get("address") or {}).get("city") or "")
    if venue_name and city:
        venue_name = f"{venue_name}, {city}"
    networks: List[str] = []
    for broadcast in comp.get("broadcasts") or []:
        for name in broadcast.get("names") or []:
            if name and name not in networks:
                networks.append(str(name))
    title = " · ".join(part for part in (matchup, venue_name, ", ".join(networks)) if part)
    odds = (comp.get("odds") or [{}])[0]
    total = odds.get("overUnder")
    spread_parts = []
    total_parts = []
    for side in ("away", "home"):
        quote = ((odds.get("pointSpread") or {}).get(side) or {}).get("close") or {}
        if quote.get("line") and sides.get(side):
            juice = f" ({quote['odds']})" if quote.get("odds") else ""
            spread_parts.append(f"{sides[side]['abbr']} {quote['line']}{juice}")
    for side in ("over", "under"):
        quote = ((odds.get("total") or {}).get(side) or {}).get("close") or {}
        if quote.get("line"):
            juice = f" ({quote['odds']})" if quote.get("odds") else ""
            total_parts.append(f"{quote['line']}{juice}")
    return {
        "venue": venue_name,
        "broadcast": ", ".join(networks),
        "spread": " · ".join(spread_parts) or str(odds.get("details") or ""),
        "total": " · ".join(total_parts) or (str(total) if total is not None else ""),
        "event_id": str(event.get("id") or comp.get("id") or ""),
        "home": sides.get("home"),
        "away": sides.get("away"),
        "neutral_site": bool(comp.get("neutralSite")),
        "state": str(status_type.get("state") or ""),
        "status_name": str(status_type.get("name") or ""),
        "status_detail": str(status_type.get("detail") or status_type.get("description") or ""),
        "period": status.get("period"),
        "clock": str(status.get("displayClock") or ""),
        "abbrs": frozenset(abbrs),
        "ids": frozenset(ids),
        "display": display,
        "iso": iso,
        "title": title,
        "done": done,
    }


def _espn_slate(league: str, day: dt.date, timeout_seconds: int = 20) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    spec = _ESPN_SCOREBOARDS.get(league)
    if spec is None:
        return [], f"no ESPN scoreboard for {league}"
    path, groups = spec
    ymd = day.strftime("%Y%m%d")
    found: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    errors = False
    for group in groups:
        query = f"dates={ymd}&limit=400"
        if group:
            query += f"&groups={group}"
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?{query}"
        try:
            payload = json.loads(_download_bytes_with_ssl(url, timeout_seconds=timeout_seconds))
            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                raise ValueError("Invalid ESPN scoreboard payload")
        except Exception:
            errors = True
            continue
        for event in payload.get("events") or []:
            game = _game_from_espn_event(event)
            if game is None:
                continue
            key = (game["event_id"],) if game["event_id"] else tuple(sorted(game["ids"])) or tuple(sorted(game["abbrs"]))
            found[key] = game
    if errors:
        return list(found.values()), f"ESPN scoreboard request failed for {league} on {day.isoformat()} (slate may be incomplete)"
    return list(found.values()), None


def _clock_label(game: Dict[str, Any], now: dt.datetime) -> Dict[str, str]:
    """Eastern start until tip, then Live. Final once ESPN marks the game done."""
    done = bool(game.get("done"))
    formatted = _format_game_start(str(game.get("iso") or ""))
    scheduled = formatted[0] if formatted else str(game.get("display") or "")
    start = dt.datetime.fromisoformat(formatted[1]) if formatted else None
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    if done:
        display = "Final"
    elif start is not None and start <= now:
        display = "Live"
    else:
        display = scheduled
    return {
        "display": display,
        "iso": formatted[1] if formatted else str(game.get("iso") or ""),
        "title": str(game.get("title") or ""),
        "done": "1" if done else "",
        "venue": str(game.get("venue") or ""),
        "broadcast": str(game.get("broadcast") or ""),
        "spread": str(game.get("spread") or "") if display not in {"Live", "Final"} and game.get("state") == "pre" else "",
        "total": str(game.get("total") or "") if display not in {"Live", "Final"} and game.get("state") == "pre" else "",
    }


def resolve_game_times(
    rows: List[Dict[str, Any]],
    fetch: Optional[Callable[[str, dt.date], Tuple[List[Dict[str, Any]], Optional[str]]]] = None,
    now: Optional[dt.datetime] = None,
) -> Tuple[Dict[Tuple[str, str, str], Dict[str, str]], List[str]]:
    """Start times for today/upcoming team cards.

    A matchup uses both teams. A single-team side, moneyline, or total uses that
    team's only game on the slate date. Parlays are skipped. The notes are the
    cards we could not place, plus one summary line for picks with no team.
    """
    fetch = fetch or _espn_slate
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    times: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    notes: List[str] = []
    no_team = 0
    slates: Dict[Tuple[str, dt.date], Tuple[List[Dict[str, Any]], Optional[str]]] = {}
    for row in rows:
        league = str(row.get("league") or "").strip().upper() or "OTHER"
        pick = str(row.get("pick") or "")
        date_text = str(row.get("date") or "").strip()
        teams, reason = _matchup_from_pick(pick, league)
        if not teams:
            if reason == "no recognized team abbreviation":
                no_team += 1
            elif reason and (
                reason == "pick names more than one matchup"
                or reason.startswith("teams are not written as one matchup")
            ):
                pass
            else:
                notes.append(f"{date_text} {league} {pick}: {reason}")
            continue
        try:
            day = dt.date.fromisoformat(date_text)
        except ValueError:
            notes.append(f"{date_text} {league} {pick}: bet date is not a slate date")
            continue
        slate_key = (league, day)
        if slate_key not in slates:
            slates[slate_key] = fetch(league, day)
        games, error = slates[slate_key]
        if error:
            notes.append(f"{date_text} {league} {pick}: {error}")
            continue
        hits = _matching_games(games, teams)
        label = " and ".join(team["name"] for team in teams)
        if len(hits) == 1:
            times[(date_text, league, pick)] = _clock_label(hits[0], now)
        elif len(hits) > 1:
            notes.append(f"{date_text} {league} {pick}: more than one game matches {label}")
        else:
            notes.append(f"{date_text} {league} {pick}: no game on the ESPN slate for {label}")
    if no_team:
        notes.append(
            f"{no_team} cards have no recognized team abbreviation, so no start time"
        )
    return times, notes


def _game_time_html(start: Optional[Dict[str, str]]) -> str:
    if not start:
        return ""
    kind = ""
    if start.get("done"):
        kind = " is-final"
    elif start.get("display") == "Live":
        kind = " is-live"
    return (
        f'<time class="today-start{kind}" datetime="{html.escape(start["iso"], quote=True)}" '
        f'title="{html.escape(start["title"], quote=True)}">{html.escape(start["display"])}</time>'
    )


def _game_info_html(start: Optional[Dict[str, str]]) -> str:
    if not start:
        return ""
    rows = "".join(f'<div class="game-info-line">{html.escape(str(value))}</div>'
                   for value in (start.get("venue"),) if value)
    if start.get("display") not in {"Live", "Final"}:
        for market in ("spread", "total"):
            value = start.get(market)
            if not value:
                continue
            quotes = []
            for quote in str(value).split(" · "):
                match = re.fullmatch(r"(.+?)\s+\(([+−-]?\d+)\)", quote)
                line, juice = match.groups() if match else (quote, "")
                if market == "total":
                    line = re.sub(r"^o(?=\d)", "Over ", line)
                    line = re.sub(r"^u(?=\d)", "Under ", line)
                quotes.append(f'<div class="game-info-quote"><span>{html.escape(line)}</span><span class="game-info-juice">{html.escape(juice)}</span></div>')
            rows += f'<div class="game-info-market">{"".join(quotes)}</div>'
    if not rows:
        return ""
    return ('<div class="game-info"><button type="button" class="game-info-trigger" aria-label="Game information">i</button>'
            f'<div class="game-info-bubble" role="tooltip">{rows}</div></div>')



def _parse_money(value: str) -> float:
    # Handles values like "$1,381.91", "-$105.05", "$105.05" or "105.05"
    s = (value or "").strip()
    if not s:
        return float("nan")
    s = s.replace("$", "").replace(",", "")
    return float(s)


def _parse_odds(value: str) -> Optional[float]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date_mmdd(value: str, year: int) -> dt.date:
    s = (value or "").strip()
    if not s:
        raise ValueError("Missing date")
    # CSV has format M/D
    month_s, day_s = s.split("/")
    return dt.date(year, int(month_s), int(day_s))


def _parse_month_day(value: str) -> Tuple[int, int]:
    s = (value or "").strip()
    if not s:
        raise ValueError("Missing date")
    month_s, day_s = s.split("/")
    return int(month_s), int(day_s)


def _american_to_implied_prob(odds: Optional[float]) -> Optional[float]:
    if odds is None:
        return None
    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return (-odds) / ((-odds) + 100.0)


def _risk_to_win_to_american_odds(risk: Optional[float], to_win: Optional[float]) -> Optional[float]:
    if risk is None or to_win is None:
        return None
    if math.isnan(risk) or math.isnan(to_win) or risk <= 0 or to_win <= 0:
        return None
    if to_win >= risk:
        return 100.0 * (to_win / risk)
    return -100.0 * (risk / to_win)


def read_bets(csv_path: str, start_year: int = 2026) -> List[Bet]:
    bets: List[Bet] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"D", "Pick", "Odds", "Risk", "Wins", "R", "Net", "Book", "League", "Type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"bets.csv missing columns: {sorted(missing)}")

        current_year = start_year
        last_month_day: Optional[Tuple[int, int]] = None

        for row in reader:
            date_cell = (row.get("D", "") or "").strip()
            if not date_cell:
                continue
            month_day = _parse_month_day(date_cell)
            if last_month_day is not None and month_day < last_month_day:
                current_year += 1
            last_month_day = month_day

            bet = Bet(
                date=dt.date(current_year, month_day[0], month_day[1]),
                pick=(row.get("Pick", "") or "").strip(),
                odds_american=_parse_odds(row.get("Odds", "")),
                risk=_parse_money(row.get("Risk", "")),
                to_win=_parse_money(row.get("Wins", "")),
                result=(row.get("R", "") or "").strip().upper(),
                net=_parse_money(row.get("Net", "")),
                book=(row.get("Book", "") or "").strip(),
                league=(row.get("League", "") or "").strip(),
                bet_type=(row.get("Type", "") or "").strip(),
            )
            bets.append(bet)
    return bets


def _nan_to_zero(x: float) -> float:
    return 0.0 if (isinstance(x, float) and math.isnan(x)) else x


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _finite_float(value: Any) -> Optional[float]:
    if value is None or _is_nan(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _sum_finite(values: Any) -> float:
    total = 0.0
    for value in values:
        number = _finite_float(value)
        if number is not None:
            total += number
    return total


def _counts_in_pl(bet: Bet) -> bool:
    # Open bets have no result and a blank net. They stay out of profit, ROI, and streaks.
    return bool(bet.result) and _finite_float(bet.net) is not None


RESULT_LABELS = {
    "W": "W",
    "L": "L",
    "P": "P",
    "CO": "Cash Out",
}


def _result_label(result: str) -> str:
    code = (result or "").strip().upper()
    if not code:
        return ""
    return RESULT_LABELS.get(code, code)


_RESULT_MARK_CLASS = {
    "W": "result-win",
    "L": "result-loss",
    "P": "result-push",
    "CO": "result-cash",
}


def _result_mark_html(result: str) -> str:
    label = _result_label(result)
    if not label:
        return ""
    code = (result or "").strip().upper()
    cls = _RESULT_MARK_CLASS.get(code, "result-other")
    return f'<span class="result-mark {cls}">{html.escape(label)}</span>'


def _net_class(value: Any) -> str:
    number = _finite_float(value)
    if number is None or number == 0:
        return ""
    return "positive" if number > 0 else "negative"


def _edge_class(edge: Optional[float]) -> str:
    if edge is None or _is_nan(edge):
        return ""
    if edge > 0:
        return "positive"
    if edge < 0:
        return "negative"
    return ""


def _fmt_edge(edge: Optional[float]) -> str:
    if edge is None or _is_nan(edge):
        return "n/a"
    return f"{edge * 100.0:+.2f} pts"


def _record_note(counts: Dict[str, Any]) -> str:
    return (
        f"Resolved: {counts['resolved']} | Open: {counts['open']} | "
        f"Push: {counts['pushes']} | Cash out: {counts['cash_outs']}"
    )


def _edge_note(avgs: Dict[str, Any]) -> str:
    win_rate = _fmt_pct(avgs.get("win_rate")) or "n/a"
    implied = _fmt_pct(avgs.get("avg_implied_prob")) or "n/a"
    return f"Win {win_rate} vs implied {implied} (edge {_fmt_edge(avgs.get('edge'))})"


def _money_net_cell(value: Any) -> Any:
    number = _finite_float(value)
    if number is None:
        return ""
    text = _fmt_money(number)
    css = _net_class(number)
    if css:
        return (text, css)
    return text


def _download_bytes(url: str, timeout_seconds: int = 30) -> bytes:
    return _download_bytes_with_ssl(url, timeout_seconds=timeout_seconds, insecure=False)


def _download_bytes_with_ssl(url: str, timeout_seconds: int = 30, insecure: bool = False) -> bytes:
    context: Optional[ssl.SSLContext] = None
    if insecure:
        context = ssl._create_unverified_context()
    else:
        try:
            import certifi  # type: ignore

            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = ssl.create_default_context()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "betting-analysis-sync/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds, context=context) as resp:
        return resp.read()


def _atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_bets_", suffix=".csv", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _safe_div(n: float, d: float) -> Optional[float]:
    if d == 0 or math.isnan(d):
        return None
    return n / d


def _period_metrics(bets: List[Bet], start_date: dt.date, end_date: dt.date, days: int) -> Dict[str, Any]:
    window = [b for b in bets if start_date <= b.date <= end_date]
    resolved = [b for b in window if b.result in {"W", "L"}]
    wins = sum(1 for b in resolved if b.result == "W")
    losses = sum(1 for b in resolved if b.result == "L")
    pushes = sum(1 for b in window if b.result == "P")
    open_count = sum(1 for b in window if not b.result)
    other = sum(1 for b in window if b.result and b.result not in {"W", "L", "P", "CO"})
    pl = [b for b in window if _counts_in_pl(b)]
    risk = sum(_nan_to_zero(b.risk) for b in pl)
    net = sum(b.net for b in pl)
    return {
        "label": f"Last {days} days",
        "days": days,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "bets": len(window),
        "resolved": len(resolved),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "open": open_count,
        "other": other,
        "risk": risk,
        "net": net,
        "roi": _safe_div(net, risk),
        "win_rate": _safe_div(wins, len(resolved)),
    }


def _longest_sign_streak(entries: List[Tuple[str, int]]) -> Dict[str, Any]:
    best_win_len = 0
    best_loss_len = 0
    best_win_start: Optional[str] = None
    best_win_end: Optional[str] = None
    best_loss_start: Optional[str] = None
    best_loss_end: Optional[str] = None

    current_sign = 0
    current_len = 0
    current_start: Optional[str] = None

    for label, sign in entries:
        if sign == 0:
            current_sign = 0
            current_len = 0
            current_start = None
            continue
        if sign == current_sign:
            current_len += 1
        else:
            current_sign = sign
            current_len = 1
            current_start = label

        if sign > 0 and current_len > best_win_len:
            best_win_len = current_len
            best_win_start = current_start
            best_win_end = label
        elif sign < 0 and current_len > best_loss_len:
            best_loss_len = current_len
            best_loss_start = current_start
            best_loss_end = label

    # Current active streak from the end of the sequence.
    current_type = ""
    current_start_out: Optional[str] = None
    current_end_out: Optional[str] = None
    current_len_out = 0

    i = len(entries) - 1
    while i >= 0 and entries[i][1] == 0:
        i -= 1
    if i >= 0:
        current_sign = entries[i][1]
        current_end_out = entries[i][0]
        j = i
        while j >= 0 and entries[j][1] == current_sign:
            j -= 1
        current_len_out = i - j
        current_start_out = entries[j + 1][0]
        current_type = "win" if current_sign > 0 else "loss"

    return {
        "current": {
            "type": current_type,
            "length": current_len_out,
            "start": current_start_out,
            "end": current_end_out,
        },
        "best_win": {
            "length": best_win_len,
            "start": best_win_start,
            "end": best_win_end,
        },
        "best_loss": {
            "length": best_loss_len,
            "start": best_loss_start,
            "end": best_loss_end,
        },
    }


def summarize(bets: List[Bet]) -> Dict[str, Any]:
    resolved = [b for b in bets if b.result in {"W", "L"}]
    pushes = [b for b in bets if b.result == "P"]
    cash_outs = [b for b in bets if b.result == "CO"]
    open_bets = [b for b in bets if not b.result]
    other = [b for b in bets if b.result and b.result not in {"W", "L", "P", "CO"}]
    pl_bets = [b for b in bets if _counts_in_pl(b)]

    total_risk = sum(_nan_to_zero(b.risk) for b in pl_bets)
    total_net = sum(b.net for b in pl_bets)
    roi = _safe_div(total_net, total_risk)

    wins = [b for b in resolved if b.result == "W"]
    losses = [b for b in resolved if b.result == "L"]

    win_rate = _safe_div(len(wins), len(resolved))

    avg_risk = _safe_div(sum(_nan_to_zero(b.risk) for b in bets), len(bets))
    avg_odds = _safe_div(
        sum(b.odds_american for b in bets if b.odds_american is not None),
        sum(1 for b in bets if b.odds_american is not None),
    )

    decided_implied = [
        p
        for b in resolved
        if (p := _american_to_implied_prob(b.odds_american)) is not None
    ]
    avg_implied = _safe_div(sum(decided_implied), float(len(decided_implied))) if decided_implied else None
    edge = None if win_rate is None or avg_implied is None else win_rate - avg_implied

    by_league = group_metrics(bets, key_fn=lambda b: b.league)
    by_book = group_metrics(bets, key_fn=lambda b: b.book)
    by_type = group_metrics(bets, key_fn=lambda b: b.bet_type)

    # cumulative net by date
    net_by_date: Dict[dt.date, float] = defaultdict(float)
    risk_by_date: Dict[dt.date, float] = defaultdict(float)
    stake_by_date: Dict[dt.date, float] = defaultdict(float)
    count_by_date: Dict[dt.date, int] = defaultdict(int)
    for b in bets:
        count_by_date[b.date] += 1
        stake_by_date[b.date] += _nan_to_zero(b.risk)
        if not _counts_in_pl(b):
            continue
        net_by_date[b.date] += b.net
        risk_by_date[b.date] += _nan_to_zero(b.risk)

    dates_sorted = sorted(net_by_date.keys())
    cum_net = 0.0
    cum_risk = 0.0
    series = []
    for d in dates_sorted:
        cum_net += net_by_date[d]
        cum_risk += risk_by_date[d]
        series.append(
            {
                "date": d.isoformat(),
                "net": net_by_date[d],
                "risk": risk_by_date[d],
                "cum_net": cum_net,
                "cum_risk": cum_risk,
                "cum_roi": (cum_net / cum_risk) if cum_risk else None,
            }
        )

    settled_bets = [b for b in bets if b.result]
    settled_dates = sorted({b.date for b in settled_bets})
    settled_net_by_date: Dict[dt.date, float] = defaultdict(float)
    for b in settled_bets:
        settled_net_by_date[b.date] += _nan_to_zero(b.net)

    daily_entries: List[Tuple[str, int]] = []
    for d in settled_dates:
        net = settled_net_by_date[d]
        sign = 1 if net > 0 else (-1 if net < 0 else 0)
        daily_entries.append((d.isoformat(), sign))
    daily_streaks = _longest_sign_streak(daily_entries)

    all_dates = [b.date for b in bets]
    today = dt.date.today()
    non_future_dates = [d for d in all_dates if d <= today]
    as_of = max(non_future_dates) if non_future_dates else (max(all_dates) if all_dates else today)

    recent_periods = []
    for days in (7, 14, 30):
        start = as_of - dt.timedelta(days=days - 1)
        recent_periods.append(_period_metrics(bets, start, as_of, days))

    recent_daily_series: List[Dict[str, Any]] = []
    for i in range(29, -1, -1):
        d = as_of - dt.timedelta(days=i)
        recent_daily_series.append(
            {
                "date": d.isoformat(),
                "net": net_by_date.get(d, 0.0),
                "risk": risk_by_date.get(d, 0.0),
            }
        )

    recent_7_day_calendar: List[Dict[str, Any]] = []
    for i in range(6, -1, -1):
        d = as_of - dt.timedelta(days=i)
        recent_7_day_calendar.append(
            {
                "date": d.isoformat(),
                "net": net_by_date.get(d, 0.0),
                "risk": stake_by_date.get(d, 0.0),
                "bets": count_by_date.get(d, 0),
            }
        )

    best_day = None
    worst_day = None
    if settled_dates:
        best_date = max(settled_dates, key=lambda d: settled_net_by_date[d])
        worst_date = min(settled_dates, key=lambda d: settled_net_by_date[d])
        best_day = {"date": best_date.isoformat(), "net": settled_net_by_date[best_date]}
        worst_day = {"date": worst_date.isoformat(), "net": settled_net_by_date[worst_date]}

    top_wins = sorted(
        [b for b in bets if not math.isnan(b.net) and b.net > 0],
        key=lambda b: b.net,
        reverse=True,
    )[:10]
    top_losses = sorted(
        [b for b in bets if not math.isnan(b.net) and b.net < 0],
        key=lambda b: b.net,
    )[:10]
    longest_shots = sorted(
        [b for b in bets if b.result == "W" and b.odds_american is not None],
        key=lambda b: (_american_to_implied_prob(b.odds_american) if _american_to_implied_prob(b.odds_american) is not None else 1.0),
    )[:10]

    settled_bets_sorted = sorted(settled_bets, key=lambda b: b.date, reverse=True)[:50]
    open_bets_sorted = sorted(open_bets, key=lambda b: b.date, reverse=True)
    all_bets_sorted = sorted(bets, key=lambda b: b.date, reverse=True)
    open_exposure = sum(_nan_to_zero(b.risk) for b in open_bets)

    today = dt.date.today()
    today_open = [b for b in open_bets if b.date == today]
    today_settled = [b for b in settled_bets if b.date == today]
    future_open = [b for b in open_bets if b.date > today]

    return {
        "as_of": as_of.isoformat(),
        "counts": {
            "total": len(bets),
            "resolved": len(resolved),
            "wins": len(wins),
            "losses": len(losses),
            "pushes": len(pushes),
            "cash_outs": len(cash_outs),
            "open": len(open_bets),
            "other": len(other),
        },
        "totals": {
            "risk": total_risk,
            "net": total_net,
            "roi": roi,
        },
        "averages": {
            "avg_risk": avg_risk,
            "avg_odds": avg_odds,
            "avg_implied_prob": avg_implied,
            "win_rate": win_rate,
            "edge": edge,
        },
        "recent_periods": recent_periods,
        "recent_daily_series": recent_daily_series,
        "recent_7_day_calendar": recent_7_day_calendar,
        "open_exposure": open_exposure,
        "streaks": {
            "daily": daily_streaks,
        },
        "best_day": best_day,
        "worst_day": worst_day,
        "by_league": by_league,
        "by_book": by_book,
        "by_type": by_type,
        "series": series,
        "top_wins": [bet_to_row(b) for b in top_wins],
        "top_losses": [bet_to_row(b) for b in top_losses],
        "longest_shots": [bet_to_row(b) for b in longest_shots],
        "recently_settled": [bet_to_row(b) for b in settled_bets_sorted],
        "open_bets": [bet_to_row(b) for b in open_bets_sorted],
        "all_bets": [bet_to_row(b) for b in all_bets_sorted],
        "today_open": [bet_to_row(b) for b in sorted(today_open, key=lambda b: b.date, reverse=True)],
        "today_settled": [bet_to_row(b) for b in sorted(today_settled, key=lambda b: b.date, reverse=True)],
        "future_open": [bet_to_row(b) for b in sorted(future_open, key=lambda b: b.date)],
    }


def bet_to_row(b: Bet) -> Dict[str, Any]:
    return {
        "date": b.date.isoformat(),
        "pick": b.pick,
        "odds": b.odds_american,
        "risk": b.risk,
        "to_win": b.to_win,
        "result": b.result,
        "net": b.net,
        "book": b.book,
        "league": b.league,
        "type": b.bet_type,
    }


def group_metrics(bets: List[Bet], key_fn) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Bet]] = defaultdict(list)
    for b in bets:
        k = (key_fn(b) or "").strip() or "(blank)"
        groups[k].append(b)

    rows: List[Dict[str, Any]] = []
    for k, bs in groups.items():
        pl = [b for b in bs if _counts_in_pl(b)]
        risk = sum(_nan_to_zero(b.risk) for b in pl)
        net = sum(b.net for b in pl)
        resolved = [b for b in bs if b.result in {"W", "L"}]
        wins = sum(1 for b in resolved if b.result == "W")
        win_rate = (wins / len(resolved)) if resolved else None
        roi = (net / risk) if risk else None
        implied_vals = [
            p
            for b in resolved
            if (p := _american_to_implied_prob(b.odds_american)) is not None
        ]
        avg_implied = (sum(implied_vals) / len(implied_vals)) if implied_vals else None
        edge = (win_rate - avg_implied) if win_rate is not None and avg_implied is not None else None
        rows.append(
            {
                "key": k,
                "count": len(bs),
                "resolved": len(resolved),
                "wins": wins,
                "losses": sum(1 for b in resolved if b.result == "L"),
                "risk": risk,
                "net": net,
                "roi": roi,
                "win_rate": win_rate,
                "avg_implied_prob": avg_implied,
                "edge": edge,
            }
        )

    rows.sort(key=lambda r: (r["net"], r["count"]), reverse=True)
    return rows


def _fmt_money(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"${x:,.2f}"


def _fmt_money_compact(x: Optional[float]) -> str:
    return _fmt_money(x).removesuffix(".00")


def _fmt_pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"{x * 100.0:.2f}%"


def _fmt_num(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if float(x).is_integer():
        return str(int(x))
    return f"{x:.2f}"


def _fmt_odds(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if float(x).is_integer():
        return f"{int(x):+d}"
    return f"{x:+.2f}"


def _round_half_away_from_zero(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _fmt_date_short(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    try:
        d = dt.date.fromisoformat(s)
        return f"{d:%b} {d.day}"
    except ValueError:
        return s


def _render_table(headers: List[str], rows: List[List]) -> str:
    ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = []
        for c in r:
            if isinstance(c, tuple):
                formatted, cls = c
                tds.append(f'<td class="{cls}">{formatted}</td>')
            else:
                tds.append(f"<td>{c}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def _normalize_pick(value: str) -> str:
    return " ".join((value or "").strip().split()).upper()


def _unique_nonblank(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        label = (v or "").strip() or "(blank)"
        key = label.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _collapse_bet_rows(bet_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str, str, str]] = []

    for r in bet_rows:
        date = str(r.get("date", "")).strip()
        pick = str(r.get("pick", "")).strip()
        league = str(r.get("league", "")).strip()
        bet_type = str(r.get("type", "")).strip()
        result = str(r.get("result", "")).strip().upper()

        key = (date, _normalize_pick(pick), league.upper(), bet_type.upper(), result)
        if key not in grouped:
            grouped[key] = {
                "date": date,
                "pick": pick,
                "type": bet_type,
                "result": result,
                "books": [],
                "leagues": [],
                "odds_values": [],
                "risk_values": [],
                "to_win_values": [],
                "net_values": [],
                "count": 0,
            }
            order.append(key)

        g = grouped[key]
        g["count"] += 1
        g["books"].append(str(r.get("book", "")).strip())
        g["leagues"].append(league)

        odds = r.get("odds")
        if odds is not None and not (isinstance(odds, float) and math.isnan(odds)):
            g["odds_values"].append(float(odds))

        risk = r.get("risk")
        if risk is not None and not (isinstance(risk, float) and math.isnan(risk)):
            g["risk_values"].append(float(risk))

        to_win = r.get("to_win")
        if to_win is not None and not (isinstance(to_win, float) and math.isnan(to_win)):
            g["to_win_values"].append(float(to_win))

        net = r.get("net")
        if net is not None and not (isinstance(net, float) and math.isnan(net)):
            g["net_values"].append(float(net))

    collapsed: List[Dict[str, Any]] = []
    for key in order:
        g = grouped[key]
        books = _unique_nonblank(g["books"])
        leagues = _unique_nonblank(g["leagues"])
        odds_values = g["odds_values"]
        risk_values = g["risk_values"]
        to_win_values = g["to_win_values"]
        net_values = g["net_values"]
        total_risk = sum(risk_values) if risk_values else float("nan")
        total_to_win = sum(to_win_values) if to_win_values else float("nan")
        display_odds: Optional[float]
        if g["count"] == 1:
            display_odds = odds_values[0] if odds_values else None
        else:
            has_complete_payout_data = len(risk_values) == g["count"] and len(to_win_values) == g["count"]
            display_odds = _risk_to_win_to_american_odds(total_risk, total_to_win) if has_complete_payout_data else None
            if display_odds is None and odds_values:
                display_odds = sum(odds_values) / len(odds_values)
        if display_odds is not None:
            display_odds = float(_round_half_away_from_zero(display_odds))

        collapsed.append(
            {
                "date": g["date"],
                "pick": g["pick"],
                "odds": display_odds,
                "risk": total_risk,
                "to_win": total_to_win,
                "result": g["result"],
                "net": (sum(net_values) if net_values else float("nan")),
                "book": books[0] if len(books) == 1 else f"{len(books)} books",
                "books": books,
                "league": leagues[0] if len(leagues) == 1 else "Mixed",
                "leagues": leagues,
                "type": g["type"],
                "row_count": g["count"],
            }
        )
    return collapsed


def build_html_report(
    summary: Dict[str, Any],
    title: str,
    league_summaries: Dict[str, Dict[str, Any]],
    default_sport: str,
    logo_base_href: str = "logos",
    available_logo_files: Optional[set[str]] = None,
    game_times: Optional[Dict[Tuple[str, str, str], Dict[str, str]]] = None,
) -> str:
    as_of = summary["as_of"]
    synced_at = dt.datetime.now().astimezone()
    last_synced = synced_at.strftime("%I:%M %p %Z").lstrip("0")
    counts = summary["counts"]
    totals = summary["totals"]
    avgs = summary["averages"]
    today_label = f"{dt.date.today():%b} {dt.date.today().day}, {dt.date.today().year}"
    today_rows = summary["today_open"] + summary["today_settled"]
    # Share the scale across both panels and keep it stable when filtering or sorting.
    displayed_risks = [
        _finite_float(row.get("risk")) or 0.0
        for rows in (today_rows, summary["future_open"])
        for row in _collapse_bet_rows(rows)
    ]
    risk_scale_max = max(displayed_risks, default=0.0)
    today_net_total = _sum_finite(r.get("net") for r in summary["today_settled"])
    today_risk_total = _sum_finite(r.get("risk") for r in today_rows)
    today_open_risk = _sum_finite(r.get("risk") for r in summary["today_open"])
    if default_sport not in league_summaries and league_summaries:
        default_sport = next(iter(league_summaries.keys()))
    default_sport_summary = league_summaries.get(default_sport, summarize([]))

    series_json = json.dumps(summary["series"])
    recent_series_json = json.dumps(summary["recent_daily_series"])

    def league_badge(league: str) -> str:
        return _league_badge(
            league,
            logo_base_href=logo_base_href,
            available_logo_files=available_logo_files,
        )

    def book_badge(book: str) -> str:
        return _book_badge(
            book,
            logo_base_href=logo_base_href,
            available_logo_files=available_logo_files,
        )

    def bet_view_controls(panel_key: str, label: str) -> str:
        return f'''<div class="today-view" role="group" aria-label="{label}" hidden>
              <button type="button" data-today-view="cards" aria-pressed="true" aria-controls="{panel_key}-bets"><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="5" height="5" rx="1"/><rect x="10" y="1" width="5" height="5" rx="1"/><rect x="1" y="10" width="5" height="5" rx="1"/><rect x="10" y="10" width="5" height="5" rx="1"/></svg>Cards</button>
              <button type="button" data-today-view="list" aria-pressed="false" aria-controls="{panel_key}-bets"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3h10M5 8h10M5 13h10M1 3h1M1 8h1M1 13h1"/></svg>List</button>
            </div>'''

    def bet_cards(bet_rows: List[Dict[str, Any]], panel_key: str = "today") -> str:
        upcoming = panel_key == "upcoming"
        context = "upcoming bets" if upcoming else "today’s bets"
        if not bet_rows:
            message = "No upcoming open bets." if upcoming else "No bets today. Today’s wagers will appear here after the next sync."
            return f'<p class="today-empty">{message}</p>'

        def league_style(league: str) -> str:
            color = LEAGUE_CARD_COLOR_MAP.get(league, LEAGUE_CARD_COLOR_MAP["OTHER"])
            rgb = ",".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
            return f"--league-color:{color};--league-rgb:{rgb}"

        rows = _collapse_bet_rows(bet_rows)

        def card_sort_key(row: Dict[str, Any]) -> Tuple[float, float]:
            league = str(row.get("league") or "").strip().upper() or "OTHER"
            start = (game_times or {}).get((row["date"], league, row["pick"])) or {}
            formatted = _format_game_start(str(start.get("iso") or ""))
            timestamp = dt.datetime.fromisoformat(formatted[1]).timestamp() if formatted else float("inf")
            risk = _finite_float(row.get("risk"))
            return timestamp, -risk if risk is not None else float("inf")

        # Keep unknown starts last, and larger combined stakes first at each start.
        rows.sort(key=card_sort_key)
        league_names = sorted({str(r.get("league") or "").strip().upper() or "OTHER" for r in rows})
        filters = [f'<button type="button" data-today-league="" aria-pressed="true" aria-controls="{panel_key}-bets">All</button>']
        for league in league_names:
            filters.append(f'<button type="button" data-today-league="{html.escape(league, quote=True)}" style="{league_style(league)}" aria-pressed="false" aria-controls="{panel_key}-bets"><span class="today-league-dot" aria-hidden="true"></span>{html.escape(league)}</button>')
        items = {status: {"straight": [], "parlay": []} for status in (["open"] if upcoming else ["open", "closed"])}
        statuses = {
            "": ("open", "Open", "◷"),
            "W": ("won", "Won", "✓"),
            "L": ("lost", "Lost", "×"),
            "P": ("push", "Push", "—"),
            "CO": ("cash-out", "Cash Out", "↗"),
        }
        for card_index, r in enumerate(rows):
            result = str(r.get("result") or "").strip().upper()
            state, label, icon = statuses.get(result, ("other", _result_label(result), "—"))
            result_badge = (
                f'<span class="today-result"><span aria-hidden="true">{icon}</span> {html.escape(label)}</span>'
                if result else ""
            )
            league_marks = []
            for card_league in r["leagues"]:
                logo_href = _logo_href(card_league, LEAGUE_LOGO_MAP, logo_base_href, available_logo_files)
                mark = (f'<img src="{html.escape(logo_href, quote=True)}" alt="" loading="lazy" decoding="async" />'
                        if logo_href else html.escape(card_league))
                league_marks.append(f'<span class="today-sport-mark" role="img" aria-label="{html.escape(card_league, quote=True)}">{mark}</span>')
            sport_watermark = f'<span class="today-sport-watermark">{"".join(league_marks)}</span>' 
            books = "".join(book_badge(x) for x in r["books"])
            amount = r.get("net") if result else r.get("to_win")
            amount_value = _finite_float(amount)
            amount_text = _fmt_money_compact(amount_value) or "—"
            if result and amount_value is not None:
                amount_text = ("+" if amount_value > 0 else "−" if amount_value < 0 else "") + _fmt_money_compact(abs(amount_value))
            amount_class = _net_class(amount_value) if result and amount_value is not None else ""
            risk_value = _finite_float(r.get("risk"))
            risk_style = ""
            if risk_value is not None:
                intensity = min(1.0, max(0.0, risk_value / risk_scale_max)) if risk_scale_max > 0 else 0.0
                # Interpolate teal → amber → coral, instead of discrete risk tiers.
                stops = ((113, 204, 190), (234, 196, 119), (242, 133, 128))
                lower, upper = (stops[0], stops[1]) if intensity <= 0.5 else (stops[1], stops[2])
                blend = intensity * 2 if intensity <= 0.5 else (intensity - 0.5) * 2
                rgb = ",".join(str(round(a + (b - a) * blend)) for a, b in zip(lower, upper))
                risk_style = f' style="--risk-rgb:{rgb};--risk-alpha:{0.07 + 0.08 * intensity:.3f}"'
            risk_tooltip = ""
            if risk_value is not None:
                unit_text = f"{risk_value / 100:.2f}".removesuffix(".00")
                risk_tooltip = f' title="{unit_text}u · 1u = $100"'
            league = str(r.get("league") or "").strip().upper() or "OTHER"
            date_label = ""
            if upcoming:
                date_label = f'<time datetime="{html.escape(r["date"], quote=True)}">{html.escape(_fmt_date_short(r["date"]))}, {html.escape(r["date"][:4])}</time>'
            bet_section = "parlay" if str(r.get("type") or "").strip().casefold() in {"parlay", "round robin"} else "straight"
            odds_text = html.escape(_fmt_odds(r.get("odds"))) or "—"
            pick_label = _today_pick_text(r["pick"], league, available_logo_files)
            pick_tooltip = html.escape(f'{pick_label} · {_fmt_odds(r.get("odds")) or "—"}', quote=True)
            pick_html = _today_pick_html(r["pick"], league, logo_base_href, available_logo_files)
            compact_pick = ""
            pick_title = f' title="{pick_tooltip}"'
            if bet_section == "parlay":
                leg_count = _parlay_leg_count(r["pick"])
                wager_label = "round robin" if str(r.get("type") or "").strip().casefold() == "round robin" else "parlay"
                compact_label = f"{leg_count} way {wager_label}" if leg_count else wager_label.title()
                details_id = f"{panel_key}-bet-{card_index}-details"
                details = f'{wager_label.title()}: {html.escape(r["pick"])}'
                compact_pick = (
                    f'<button type="button" class="compact-pick" aria-describedby="{details_id}" hidden>'
                    f'{compact_label}<span class="pick-details-icon" aria-hidden="true">ⓘ</span></button>'
                    f'<span id="{details_id}" class="pick-details" role="tooltip">{details} · {odds_text}</span>'
                )
                pick_title = ""
            start = (game_times or {}).get((r["date"], league, r["pick"]))
            game_info = _game_info_html(start)
            start_html = _game_time_html(start)
            broadcast = str((start or {}).get("broadcast") or "").split(",", 1)[0].strip()
            network_files = {
                "espn": "ESPN_logos.png", "espn+": "ESPN-PNG-File.png",
                "youtube": "Youtube_logo.png", "fox": "fox.svg", "fs1": "fs1.png",
                "acc network": "accn.png", "accnx": "accn.png",
                "sec network": "secn.png", "secn+": "secn.png",
                "flosports": "FloSports-logo.png",
            }
            network_file = network_files.get(broadcast.casefold())
            network_href = _join_href(logo_base_href, f"networks/{network_file}") if network_file else ""
            if network_file and available_logo_files is not None and f"networks/{network_file}".lower() not in available_logo_files:
                network_href = ""
            network_mark = (f'<img class="today-network-logo" src="{html.escape(network_href, quote=True)}" alt="{html.escape(broadcast, quote=True)}" decoding="async" />'
                            if network_href else html.escape(broadcast))
            broadcast_html = f'<span class="today-broadcast-separator" aria-hidden="true">|</span><span class="today-broadcast" title="{html.escape(broadcast, quote=True)}">{network_mark}</span>' if broadcast else ""
            when_html = f'<div class="today-when">{start_html}{broadcast_html}</div>' if start_html else ""
            start_timestamp = card_sort_key(r)[0]
            start_ms = str(int(start_timestamp * 1000)) if math.isfinite(start_timestamp) else ""
            game_done = bool(start and start.get("done")) and not upcoming
            items["closed" if result or game_done else "open"][bet_section].append(f'''<li class="today-bet today-bet--{state}" data-league="{html.escape(league, quote=True)}" style="{league_style(league)}" data-start-ms="{start_ms}" data-risk="{_sum_finite([r.get('risk')])}" data-net="{_sum_finite([r.get('net')]) if result else 0}" data-potential="{_sum_finite([r.get('to_win')]) if not result else 0}" data-count="{r['row_count']}" data-open="{str(not result).lower()}">
              {sport_watermark}
              <div class="today-bet-body">
                <div class="today-pick-line"{pick_title}><h4 class="today-pick">{pick_html}</h4>{compact_pick}<span class="today-odds" title="Odds"><strong>{odds_text}</strong></span></div>
                <div class="today-meta">{date_label}</div>
              </div>
              <div class="today-bet-top">
                <div class="today-league">{result_badge}</div>
                <div class="chip-row today-logos">{game_info}{books}</div>
              </div>
              <dl class="today-bet-money">
                <div class="today-stake"{risk_style}><dt>Risk</dt><dd><span class="today-risk-amount"{risk_tooltip}>{_fmt_money_compact(r.get("risk")) or "—"}</span></dd></div>
                {when_html}
                <div class="today-return"><dt{(' class="today-net-label"' if result else '')}>{"Net result" if result else "wins"}</dt><dd class="{amount_class}">{amount_text}</dd></div>
              </dl>
            </li>''')
        group_markup = []
        for status, sections in items.items():
            count = sum(len(bets) for bets in sections.values())
            section_markup = []
            for kind, bets in sections.items():
                if not bets:
                    continue
                label = "Parlays" if kind == "parlay" else "Straight"
                section_id = f"{panel_key}-{status}-{kind}-title"
                section_markup.append(
                    f'<div class="today-bet-section" data-bet-section="{kind}" role="group" aria-labelledby="{section_id}">'
                    f'<h4 id="{section_id}" class="today-bet-section-title">{label}</h4>'
                    f'<ul class="today-bets" aria-label="{status.title()} {label.lower()} bets">{"".join(bets)}</ul></div>'
                )
            tag = "details" if status == "closed" else "div"
            heading = "summary" if status == "closed" else "h3"
            role = ' role="group"' if status == "open" else ""
            group_markup.append(
                f'<{tag} class="today-group" data-today-group="{status}"{role} aria-labelledby="{panel_key}-{status}-title"{(" open" if status == "closed" else "")}{(" hidden" if not count else "")}>'
                f'<{heading} id="{panel_key}-{status}-title" class="today-group-title">{status.title()} <span class="today-group-count">{count}</span></{heading}>'
                f'{"".join(section_markup)}</{tag}>'
            )
        groups = "".join(group_markup)
        return (
            '<div class="today-filter-bar" hidden><div class="today-filter-controls">'
            + f'<div class="today-filters" role="group" aria-label="Filter {context} by league">'
            + "".join(filters)
            + f'</div><div class="today-filters today-sort" role="group" aria-label="Sort {context}">'
            + '<span class="today-sort-label">Sort</span>'
            + f'<button type="button" data-today-sort="time" aria-pressed="true" aria-controls="{panel_key}-bets" title="Earliest start first; unknown times last">Time ↑</button>'
            + f'<button type="button" data-today-sort="risk" aria-pressed="false" aria-controls="{panel_key}-bets" title="Highest risk first">Risk ↓</button>'
            + f'</div></div><span id="{panel_key}-filter-count" class="note today-filter-count" role="status">{len(rows)} bets</span></div>'
            + f'<div id="{panel_key}-bets">' + groups
            + f'<p id="{panel_key}-filter-empty" class="today-empty" hidden>No bets match these filters.</p></div>'
        )

    def group_table(group_rows: List[Dict[str, Any]], limit: int = 25, badge_kind: str = "") -> str:
        headers = ["Group", "Bets", "W", "L", "Risk", "Net", "ROI", "Win%"]
        rows = []
        for r in group_rows[:limit]:
            net_fmt = _fmt_money(r["net"])
            net_cls = "positive" if r["net"] >= 0 else "negative"
            roi_fmt = _fmt_pct(r["roi"])
            roi_cls = _net_class(r["roi"]) if r["roi"] is not None else ""
            win_fmt = _fmt_pct(r["win_rate"])
            win_cls = _edge_class(r.get("edge"))
            key_label = str(r["key"])
            if badge_kind == "league":
                group_cell = league_badge(key_label)
            elif badge_kind == "book":
                group_cell = book_badge(key_label)
            else:
                group_cell = html.escape(key_label)
            rows.append(
                [
                    group_cell,
                    str(r["count"]),
                    str(r["wins"]),
                    str(r["losses"]),
                    _fmt_money(r["risk"]),
                    (net_fmt, net_cls),
                    (roi_fmt, roi_cls) if roi_cls else roi_fmt,
                    (win_fmt, win_cls) if win_cls else win_fmt,
                ]
            )
        return _render_table(headers, rows)

    def bets_table(
        bet_rows: List[Dict[str, Any]],
        include_result: bool = True,
        include_net: bool = True,
        collapse_duplicates: bool = True,
        show_totals: bool = False,
    ) -> str:
        rows_in = _collapse_bet_rows(bet_rows) if collapse_duplicates else bet_rows
        headers = ["Date", "League", "Book", "Type", "Pick", "Odds", "Risk"]
        if include_result:
            headers.append("Result")
        if include_net:
            headers.append("Net")
        rows = []
        total_risk = 0.0
        total_net = 0.0
        for r in rows_in:
            leagues = r.get("leagues") or [r.get("league", "")]
            books = r.get("books") or [r.get("book", "")]
            if len(leagues) == 1:
                league_cell = league_badge(leagues[0])
            else:
                league_cell = f'<div class="chip-row">{"".join(league_badge(x) for x in leagues)}</div>'
            if len(books) == 1:
                book_cell = book_badge(books[0])
            else:
                book_cell = f'<div class="chip-row">{"".join(book_badge(x) for x in books)}</div>'

            pick_cell = html.escape(r["pick"])
            row_count = int(r.get("row_count", 1) or 1)
            if row_count > 1:
                pick_cell += f'<div class="note-inline">{row_count} wagers combined</div>'

            odds_text = _fmt_odds(r.get("odds"))
            row = [
                html.escape(_fmt_date_short(r["date"])),
                league_cell,
                book_cell,
                html.escape(r["type"]),
                pick_cell,
                html.escape(odds_text),
                _fmt_money(r["risk"]),
            ]
            if include_result:
                row.append(_result_mark_html(str(r.get("result") or "")))
            if include_net:
                row.append(_money_net_cell(r.get("net")))
            rows.append(row)
            finite_risk = _finite_float(r.get("risk"))
            if finite_risk is not None:
                total_risk += finite_risk
            if include_net:
                finite_net = _finite_float(r.get("net"))
                if finite_net is not None:
                    total_net += finite_net

        if not show_totals:
            return _render_table(headers, rows)

        ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        tbody_rows = []
        for r in rows:
            tds = []
            for c in r:
                if isinstance(c, tuple):
                    formatted, cls = c
                    tds.append(f'<td class="{cls}">{formatted}</td>')
                else:
                    tds.append(f"<td>{c}</td>")
            tbody_rows.append(f"<tr>{''.join(tds)}</tr>")

        tfoot_cells = [""] * len(headers)
        tfoot_cells[0] = '<span class="muted">Subtotal</span>'
        risk_idx = headers.index("Risk")
        tfoot_cells[risk_idx] = _fmt_money(total_risk)
        if include_net and "Net" in headers:
            net_idx = headers.index("Net")
            net_cls = _net_class(total_net)
            net_text = _fmt_money(total_net)
            if net_cls:
                tfoot_cells[net_idx] = f'<span class="{net_cls}">{net_text}</span>'
            else:
                tfoot_cells[net_idx] = net_text
        tfoot_html = "".join(f"<td>{c}</td>" for c in tfoot_cells)

        return (
            f"<table><thead><tr>{ths}</tr></thead>"
            f"<tbody>{''.join(tbody_rows)}</tbody>"
            f"<tfoot><tr>{tfoot_html}</tr></tfoot></table>"
        )

    def all_bets_table(bet_rows: List[Dict[str, Any]]) -> str:
        if not bet_rows:
            return "<div class='note'>No bets available.</div>"

        header_cols = [
            ("date", "Date", "text"),
            ("league", "League", "text"),
            ("book", "Book", "text"),
            ("type", "Type", "text"),
            ("pick", "Pick", "text"),
            ("odds", "Odds", "number"),
            ("risk", "Risk", "number"),
            ("result", "Result", "text"),
            ("net", "Net", "number"),
        ]
        thead = "".join(
            f"<th><button type='button' class='sort-btn' data-key='{key}' data-type='{kind}'>{html.escape(label)}</button></th>"
            for key, label, kind in header_cols
        )

        trs = []
        for r in bet_rows:
            league = str(r.get("league", "") or "").strip()
            book = str(r.get("book", "") or "").strip()
            bet_type = str(r.get("type", "") or "").strip()
            pick = str(r.get("pick", "") or "").strip()
            result = str(r.get("result", "") or "").strip().upper()
            date = str(r.get("date", "") or "").strip()
            odds = r.get("odds")
            risk = r.get("risk")
            net = r.get("net")

            odds_val = "" if odds is None or (isinstance(odds, float) and math.isnan(odds)) else f"{float(odds):.8f}"
            risk_val = "" if risk is None or (isinstance(risk, float) and math.isnan(risk)) else f"{float(risk):.8f}"
            net_val = "" if net is None or (isinstance(net, float) and math.isnan(net)) else f"{float(net):.8f}"

            finite_net = _finite_float(net)
            net_cls = _net_class(finite_net)

            row_attrs = (
                f"data-date='{html.escape(date, quote=True)}' "
                f"data-league='{html.escape(league, quote=True)}' "
                f"data-book='{html.escape(book, quote=True)}' "
                f"data-type='{html.escape(bet_type, quote=True)}' "
                f"data-pick='{html.escape(pick, quote=True)}' "
                f"data-odds='{html.escape(odds_val, quote=True)}' "
                f"data-risk='{html.escape(risk_val, quote=True)}' "
                f"data-result='{html.escape(result, quote=True)}' "
                f"data-net='{html.escape(net_val, quote=True)}'"
            )

            cells = [
                html.escape(_fmt_date_short(date)),
                league_badge(league),
                book_badge(book),
                html.escape(bet_type),
                html.escape(pick),
                html.escape(_fmt_odds(odds)),
                _fmt_money(risk),
                _result_mark_html(result),
                (_fmt_money(finite_net), net_cls) if net_cls else (_fmt_money(finite_net) if finite_net is not None else ""),
            ]
            tds = []
            for c in cells:
                if isinstance(c, tuple):
                    formatted, cls = c
                    tds.append(f'<td class="{cls}">{formatted}</td>')
                else:
                    tds.append(f"<td>{c}</td>")
            trs.append(f"<tr class='all-bets-row' {row_attrs}>{''.join(tds)}</tr>")

        return (
            "<div class='scroll'>"
            "<table id='all-bets-table'>"
            f"<thead><tr>{thead}</tr></thead>"
            f"<tbody>{''.join(trs)}</tbody>"
            "</table>"
            "</div>"
        )

    def period_table(period_rows: List[Dict[str, Any]]) -> str:
        headers = ["Window", "Bets", "W-L", "Win%", "Risk", "Net", "ROI", "Open"]
        rows = []
        for r in period_rows:
            net_cls = _net_class(r["net"])
            roi_cls = _net_class(r["roi"]) if r["roi"] is not None else ""
            net_text = _fmt_money(r["net"])
            roi_text = _fmt_pct(r["roi"])
            rows.append(
                [
                    html.escape(r["label"]),
                    str(r["bets"]),
                    f"{r['wins']}-{r['losses']}",
                    _fmt_pct(r["win_rate"]),
                    _fmt_money(r["risk"]),
                    (net_text, net_cls) if net_cls else net_text,
                    (roi_text, roi_cls) if roi_cls else roi_text,
                    str(r["open"]),
                ]
            )
        return _render_table(headers, rows)

    def daily_net_risk_calendar(day_rows: List[Dict[str, Any]]) -> str:
        if not day_rows:
            return '<div class="note">No recent daily data.</div>'

        cards = []
        for r in day_rows:
            date_s = str(r.get("date", "")).strip()
            try:
                d = dt.date.fromisoformat(date_s)
                day_name = f"{d:%a}"
                day_label = f"{d:%b} {d.day}"
            except ValueError:
                day_name = ""
                day_label = date_s

            net = float(r.get("net", 0.0) or 0.0)
            risk = float(r.get("risk", 0.0) or 0.0)
            bets = int(r.get("bets", 0) or 0)
            card_cls = "day-card pos" if net > 0 else ("day-card neg" if net < 0 else "day-card flat")
            net_cls = "positive" if net > 0 else ("negative" if net < 0 else "")
            bet_word = "bet" if bets == 1 else "bets"

            cards.append(
                f"""
                <div class="{card_cls}">
                  <div class="day-top">
                    <div class="day-name">{html.escape(day_name)}</div>
                    <div class="day-date">{html.escape(day_label)}</div>
                  </div>
                  <div class="day-row"><span>Net</span><strong class="{net_cls}">{_fmt_money(net)}</strong></div>
                  <div class="day-row"><span>Risk</span><strong>{_fmt_money(risk)}</strong></div>
                  <div class="day-count">{bets} {bet_word}</div>
                </div>
                """
            )
        return f'<div class="calendar-scroll"><div class="calendar-strip">{"".join(cards)}</div></div>'

    def streak_line(title_text: str, streak: Dict[str, Any]) -> str:
        if streak["length"] <= 0:
            return f"<div><strong>{html.escape(title_text)}:</strong> none</div>"
        if streak["start"] == streak["end"]:
            span = streak["start"]
        else:
            span = f"{streak['start']} to {streak['end']}"
        return f"<div><strong>{html.escape(title_text)}:</strong> {streak['length']} ({html.escape(span)})</div>"

    def current_streak_text(streak_group: Dict[str, Any]) -> str:
        current = streak_group["current"]
        if current["length"] > 0:
            return (
                f"{current['length']} {current['type']} "
                f"day(s) ({current['start']} to {current['end']})"
            )
        return "No active daily win/loss streak"

    def sport_summary_payload(league_label: str, league_summary: Dict[str, Any]) -> Dict[str, Any]:
        league_counts = league_summary["counts"]
        league_totals = league_summary["totals"]
        league_avgs = league_summary["averages"]
        league_streaks = league_summary["streaks"]
        league_best_day = league_summary["best_day"]
        league_worst_day = league_summary["worst_day"]

        best_day_text = "n/a"
        if league_best_day:
            best_day_text = f"{league_best_day['date']} ({_fmt_money(league_best_day['net'])})"

        worst_day_text = "n/a"
        if league_worst_day:
            worst_day_text = f"{league_worst_day['date']} ({_fmt_money(league_worst_day['net'])})"

        return {
            "label": league_label,
            "as_of": league_summary["as_of"],
            "counts": league_counts,
            "totals": league_totals,
            "averages": league_avgs,
            "open_exposure": league_summary["open_exposure"],
            "series": league_summary["series"],
            "recent_daily_series": league_summary["recent_daily_series"],
            "recent_periods_html": period_table(league_summary["recent_periods"]),
            "recent_calendar_html": daily_net_risk_calendar(league_summary["recent_7_day_calendar"]),
            "recently_settled_html": bets_table(league_summary["recently_settled"][:25]),
            "open_bets_html": bets_table(league_summary["open_bets"]),
            "by_book_html": group_table(league_summary["by_book"], badge_kind="book"),
            "by_type_html": group_table(league_summary["by_type"]),
            "top_wins_html": bets_table(league_summary["top_wins"], include_result=False),
            "top_losses_html": bets_table(league_summary["top_losses"], include_result=False),
            "longest_shots_html": bets_table(league_summary["longest_shots"], include_result=False),
            "daily_current_text": current_streak_text(league_streaks["daily"]),
            "streak_lines_html": "".join(
                [
                    streak_line("Longest daily win streak", league_streaks["daily"]["best_win"]),
                    streak_line("Longest daily loss streak", league_streaks["daily"]["best_loss"]),
                ]
            ),
            "best_day_text": best_day_text,
            "worst_day_text": worst_day_text,
        }

    daily_streaks = summary["streaks"]["daily"]

    daily_current_text = current_streak_text({"current": daily_streaks["current"]})

    best_day = summary["best_day"]
    worst_day = summary["worst_day"]
    sport_options = list(league_summaries.keys())
    sport_options_html = "".join(
        f"<option value=\"{html.escape(league)}\"{' selected' if league == default_sport else ''}>{html.escape(league)}</option>"
        for league in sport_options
    )
    sport_summaries_json = json.dumps(
        {league: sport_summary_payload(league, league_summary) for league, league_summary in league_summaries.items()}
    )
    default_sport_payload = sport_summary_payload(default_sport, default_sport_summary)

    html_doc = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <script src=\"https://cdn.plot.ly/plotly-2.30.0.min.js\"></script>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #0f1a2e;
      --panel2: #0c1628;
      --text: #e6eefc;
      --muted: #9db0d0;
      --border: rgba(255,255,255,0.08);
      --good: #34d399;
      --bad: #fb7185;
      --accent: #60a5fa;
    }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
    .subtitle {{ color: var(--muted); margin-bottom: 18px; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 14px; }}
    .tab-btn {{
      background: rgba(157, 176, 208, 0.15);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
    }}
    .tab-btn.active {{ background: rgba(96, 165, 250, 0.28); border-color: rgba(96, 165, 250, 0.6); }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }}
    .history-split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .history-col {{ display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
    .card {{ background: linear-gradient(180deg, var(--panel), var(--panel2)); border: 1px solid var(--border); border-radius: 14px; padding: 14px 14px; }}
    .kpi {{ grid-column: span 3; }}
    .kpi .label {{ color: var(--muted); font-size: 12px; }}
    .kpi .value {{ font-size: 20px; margin-top: 6px; font-variant-numeric: tabular-nums; }}
    .kpi .value.good {{ color: var(--good); }}
    .kpi .value.bad {{ color: var(--bad); }}
    .full {{ grid-column: span 12; }}
    .half {{ grid-column: span 6; }}
    .third {{ grid-column: span 4; }}

    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 10px 10px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
    td {{ font-size: 13px; }}
    .scroll {{ overflow-x: auto; }}
    .section-title {{ margin: 6px 0 10px; font-size: 16px; }}
    .note {{ color: var(--muted); font-size: 12px; line-height: 1.4; }}
    .row-controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
    .search-input {{
      flex: 1 1 260px;
      min-width: 220px;
      background: rgba(255,255,255,0.03);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
      box-sizing: border-box;
    }}
    .control-input {{
      box-sizing: border-box;
      width: 100%;
      min-width: 0;
      background: rgba(255,255,255,0.03);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 7px 10px;
      font-size: 12px;
      line-height: 1.25;
      min-height: 40px;
      flex: 0 0 auto;
    }}
    select.control-input {{
      appearance: none;
      background-image:
        linear-gradient(45deg, transparent 50%, var(--muted) 50%),
        linear-gradient(135deg, var(--muted) 50%, transparent 50%);
      background-position:
        calc(100% - 18px) calc(50% - 2px),
        calc(100% - 12px) calc(50% - 2px);
      background-size: 6px 6px, 6px 6px;
      background-repeat: no-repeat;
      padding-right: 28px;
    }}
    .filter-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
      align-items: end;
    }}
    .filter-field {{
      display: flex;
      flex-direction: column;
      gap: 5px;
      min-width: 0;
    }}
    .filter-label {{
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .filter-range {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .filter-actions {{
      display: flex;
      align-items: end;
      gap: 8px;
      min-width: 0;
    }}
    .filter-btn {{
      box-sizing: border-box;
      background: rgba(157, 176, 208, 0.15);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 0 14px;
      min-height: 40px;
      font-size: 12px;
      cursor: pointer;
      white-space: nowrap;
    }}
    .filter-btn:hover {{ border-color: rgba(96, 165, 250, 0.5); }}
    .all-bets-kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }}
    .sub-kpi {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      background: rgba(255,255,255,0.02);
    }}
    .sub-kpi .label {{ color: var(--muted); font-size: 11px; }}
    .sub-kpi .value {{ margin-top: 4px; font-size: 15px; font-variant-numeric: tabular-nums; }}
    .sort-btn {{
      appearance: none;
      border: 0;
      background: transparent;
      color: inherit;
      padding: 0;
      font: inherit;
      cursor: pointer;
      text-align: left;
    }}
    .sort-btn.active {{ color: var(--accent); }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.01em;
      line-height: 1.4;
      white-space: nowrap;
    }}
    .badge-logo {{
      width: 26px;
      height: 26px;
      padding: 0;
      flex-shrink: 0;
      border-radius: 7px;
      justify-content: center;
      background: rgba(255,255,255,0.96);
      border-color: rgba(15,23,42,0.16);
      overflow: hidden;
      vertical-align: middle;
    }}
    .badge-logo-img {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      object-position: center;
      transform: scale(1.1);
    }}
    /* Enlarge recognizable marks in source images with generous built-in margins. */
    .badge-logo-img[src$="nba.png"] {{ object-fit: cover; transform: scale(1.6); }}
    .badge-logo-img[src$="mlb.png"] {{ transform: scale(1.6); }}
    .badge-logo-img[src$="caesars.jpg"] {{ transform: scale(1.45); }}
    .badge-logo-img[src$="betmgm.png"] {{ transform: scale(2.1) translateY(12%); }}
    .badge-sticker {{
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
    }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .note-inline {{ color: var(--muted); font-size: 11px; margin-top: 4px; }}
    .calendar-scroll {{ overflow-x: auto; padding-bottom: 4px; }}
    .calendar-strip {{
      display: grid;
      grid-template-columns: repeat(7, minmax(128px, 1fr));
      gap: 10px;
      min-width: 920px;
    }}
    .day-card {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px;
      background: rgba(255,255,255,0.02);
    }}
    .day-card.pos {{ border-color: rgba(52,211,153,0.45); }}
    .day-card.neg {{ border-color: rgba(251,113,133,0.45); }}
    .day-card.flat {{ border-color: rgba(157,176,208,0.35); }}
    .day-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      gap: 6px;
    }}
    .day-name {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
    .day-date {{ font-size: 13px; font-weight: 700; }}
    .day-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
    }}
    .day-row strong {{ font-size: 13px; color: var(--text); }}
    .day-count {{ margin-top: 8px; font-size: 11px; color: var(--muted); }}

    .positive {{ color: var(--good); }}
    .negative {{ color: var(--bad); }}
    .result-mark {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.7em;
      padding: 1px 7px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.04em;
      line-height: 1.45;
      white-space: nowrap;
    }}
    .result-win {{
      color: #d1fae5;
      background: rgba(52, 211, 153, 0.22);
      box-shadow: inset 0 0 0 1px rgba(52, 211, 153, 0.72);
    }}
    .result-loss {{
      color: #ffe4e6;
      background: rgba(251, 113, 133, 0.22);
      box-shadow: inset 0 0 0 1px rgba(251, 113, 133, 0.72);
    }}
    .result-push, .result-cash, .result-other {{
      color: var(--text);
      background: rgba(157, 176, 208, 0.16);
      box-shadow: inset 0 0 0 1px rgba(157, 176, 208, 0.45);
    }}

    .today-panel {{ min-width: 0; padding: 12px; }}
    .today-header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; margin-bottom: 7px; }}
    .today-heading {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }}
    .today-heading h2 {{ margin: 0; font-size: 16px; }}
    .today-date {{ font-size: 12px; color: var(--muted); }}
    .today-header .note {{ margin-top: 3px; font-size: 11px; }}
    .today-view {{ display: flex; gap: 3px; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }}
    .today-view[hidden] {{ display: none; }}
    .today-filter-bar {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 10px; margin-bottom: 6px; padding-top: 6px; border-top: 1px solid var(--border); }}
    .today-filter-controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }}
    .today-filter-bar[hidden], .today-panel[data-view] .today-bet[hidden], .today-group[hidden], .today-empty[hidden] {{ display: none; }}
    .today-group + .today-group {{ margin-top: 12px; }}
    .today-group[hidden] + .today-group {{ margin-top: 0; }}
    .today-group-title {{ display: flex; align-items: center; gap: 6px; margin: 0 0 5px; font-size: 11px; font-weight: 600; color: var(--muted); }}
    .today-group-title::after {{ content: ''; height: 1px; flex: 1; background: var(--border); }}
    details.today-group > summary {{ cursor: pointer; list-style: none; min-height: 24px; margin-bottom: 0; }}
    details.today-group > summary::-webkit-details-marker {{ display: none; }}
    details.today-group > summary::before {{ content: '›'; font-size: 16px; line-height: 1; }}
    details.today-group[open] > summary {{ margin-bottom: 5px; }}
    details.today-group[open] > summary::before {{ transform: rotate(90deg); }}
    details.today-group > summary:hover {{ color: var(--text); }}
    details.today-group > summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }}
    [data-today-group="open"] .today-group-title {{ color: var(--accent); }}
    .today-group-count {{ font-weight: 400; color: var(--muted); font-variant-numeric: tabular-nums; }}
    .today-filters {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .today-filters button {{ display: inline-flex; align-items: center; gap: 5px; min-height: 26px; padding: 2px 7px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: var(--muted); font: inherit; font-size: 11px; cursor: pointer; }}
    .today-filters button:hover {{ background: rgba(255,255,255,0.04); color: var(--text); }}
    .today-filters button[aria-pressed="true"] {{ border-color: var(--border); background: rgba(255,255,255,0.06); color: var(--text); }}
    .today-filters button[data-today-league]:not([data-today-league=""])[aria-pressed="true"] {{ color: var(--league-color); border-color: rgba(var(--league-rgb),0.4); background: rgba(var(--league-rgb),0.12); }}
    .today-filters button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .today-league-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--league-color); box-shadow: 0 0 0 1px rgba(255,255,255,0.18); }}
    .today-filter-count {{ font-size: 11px; }}
    .today-sort {{ align-items: center; border-left: 1px solid var(--border); padding-left: 8px; }}
    .today-sort-label {{ color: var(--muted); font-size: 10px; margin-right: 2px; }}
    .today-view button {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--muted); padding: 5px 8px; font: inherit; font-size: 11px; cursor: pointer; }}
    .today-view button[aria-pressed="true"] {{ color: var(--text); background: rgba(96,165,250,0.18); border-color: rgba(96,165,250,0.35); }}
    .today-view button:hover {{ color: var(--text); }}
    .today-view button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .today-view svg {{ width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.5; }}
    .today-summary {{ display: flex; flex-wrap: wrap; gap: 5px 12px; margin: 0 0 0 auto; }}
    .today-summary > div {{ display: flex; align-items: baseline; gap: 6px; }}
    .today-panel dt {{ color: var(--muted); font-size: 11px; line-height: 1.4; }}
    .today-panel dd {{ margin: 3px 0 0; font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }}
    .today-summary dd {{ margin: 0; font-size: 14px; }}
    .today-summary .today-risk-value {{ color: #fbbf24; }}
    .today-bets {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; list-style: none; padding: 0; margin: 0; }}
    .today-bet-section[hidden] {{ display: none; }}
    .today-bet-section:not([hidden]) + .today-bet-section {{ margin-top: 12px; }}
    .today-bet-section-title {{ display: flex; align-items: center; gap: 8px; margin: 8px 0 6px; color: var(--muted); font-size: 10px; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; }}
    .today-bet-section-title::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}
    .today-bet {{ position: relative; isolation: isolate; --result-color: var(--muted); --result-rgb: 157, 176, 208; display: flex; flex-direction: column; min-width: 0; padding: 8px 9px; border: 1px solid rgba(var(--league-rgb),0.24); border-left: 2px solid rgba(var(--league-rgb),0.9); border-radius: 6px; background: linear-gradient(110deg, rgba(var(--league-rgb),0.12), rgba(var(--league-rgb),0.035)); box-shadow: inset 1px 0 0 rgba(var(--league-rgb),0.9); }}
    .today-sport-watermark {{ position: absolute; inset: 0; z-index: -1; display: flex; justify-content: flex-end; align-items: center; gap: 12px; overflow: hidden; border-radius: inherit; pointer-events: none; opacity: 0.085; }}
    .today-sport-mark {{ display: flex; align-items: center; justify-content: center; width: 140px; height: 100%; min-width: 0; color: var(--text); font-size: 48px; font-weight: 900; }}
    .today-sport-mark img {{ display: block; width: 100%; height: 100%; max-height: 120px; object-fit: contain; filter: grayscale(1); }}
    .today-panel[data-view="list"] .today-sport-mark {{ width: 100px; }}
    .today-bet--won {{ --result-color: var(--good); --result-rgb: 52, 211, 153; }}
    .today-bet--lost {{ --result-color: var(--bad); --result-rgb: 251, 113, 133; }}
    .today-bet-top {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
    .today-league {{ display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: var(--muted); font-size: 10px; min-width: 0; overflow-wrap: anywhere; }}
    .today-league:empty {{ display: none; }}
    .today-logos {{ justify-content: flex-end; align-items: center; gap: 3px; min-width: 0; margin-left: auto; }}
    .game-info {{ position: relative; flex: 0 0 auto; }}
    .game-info-trigger {{ display: flex; align-items: center; justify-content: center; box-sizing: border-box; width: 12px; height: 12px; padding: 0; border: 1px solid rgba(157,176,208,0.5); border-radius: 50%; background: transparent; color: var(--muted); font: 500 8px Georgia, serif; cursor: help; }}
    .game-info:hover .game-info-trigger, .game-info:focus-within .game-info-trigger {{ color: var(--text); border-color: var(--text); }}
    .game-info-trigger:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .game-info-bubble {{ display: none; position: absolute; top: calc(100% + 5px); right: 0; z-index: 8; width: min(210px, 65vw); padding: 7px 9px; border: 1px solid var(--border); border-radius: 5px; background: #111827; box-shadow: 0 6px 18px rgba(0,0,0,0.35); white-space: normal; }}
    .game-info-bubble::before {{ content: ''; position: absolute; bottom: 100%; left: 0; width: 100%; height: 5px; }}
    .game-info:hover .game-info-bubble, .game-info:focus-within .game-info-bubble {{ display: block; }}
    .game-info-bubble {{ font-size: 10px; line-height: 1.5; font-variant-numeric: tabular-nums; }}
    .game-info-line + .game-info-line {{ margin-top: 2px; color: var(--muted); }}
    .game-info-market {{ margin-top: 6px; padding-top: 5px; border-top: 1px solid var(--border); }}
    .game-info-quote {{ display: flex; justify-content: space-between; gap: 14px; }}
    .game-info-juice {{ color: var(--muted); text-align: right; }}
    .today-bet:has(.game-info:hover), .today-bet:has(.game-info:focus-within) {{ z-index: 6; }}
    .today-result {{ display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; padding: 2px 8px; border-radius: 999px; color: var(--result-color); background: rgba(var(--result-rgb), 0.18); box-shadow: inset 0 0 0 1px rgba(var(--result-rgb), 0.55); font-size: 11px; font-weight: 800; letter-spacing: 0.04em; line-height: 1.3; text-transform: uppercase; }}
    .today-bet--won .today-result, .today-bet--lost .today-result {{ background: rgba(var(--result-rgb), 0.24); box-shadow: inset 0 0 0 1px rgba(var(--result-rgb), 0.8); }}
    .today-result > span {{ font-size: 13px; line-height: 1; }}
    .today-bet-body {{ flex: 1; min-width: 0; padding: 0 0 7px; }}
    .today-pick-line {{ --pick-font-size: 13px; display: flex; align-items: baseline; gap: 6px; width: 100%; min-width: 0; white-space: nowrap; line-height: 1.35; }}
    .today-pick-line:has(.team-logo) {{ align-items: center; }}
    .today-pick {{ min-width: 0; margin: 0; font-size: var(--pick-font-size); font-weight: 700; line-height: inherit; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    [data-bet-section="parlay"] .today-pick {{ text-overflow: clip; }}
    [data-bet-section="parlay"] .today-pick-line {{ position: relative; }}
    .compact-pick {{ display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; border: 0; padding: 0; background: none; color: var(--text); font: inherit; font-size: var(--pick-font-size); font-weight: 700; cursor: help; }}
    .compact-pick[hidden], .today-pick[hidden] {{ display: none; }}
    .compact-pick:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 3px; }}
    .pick-details-icon {{ color: var(--muted); font-size: 11px; font-weight: 400; }}
    .pick-details {{ display: none; position: absolute; bottom: calc(100% + 8px); left: 0; width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: #111827; color: var(--text); font-size: 12px; font-weight: 400; line-height: 1.5; white-space: normal; overflow-wrap: anywhere; box-shadow: 0 6px 18px rgba(0,0,0,0.35); z-index: 5; }}
    .pick-details::after {{ content: ''; position: absolute; top: 100%; left: 0; width: 100%; height: 8px; }}
    .today-pick-line.is-compact:not(.details-dismissed):is(:hover, :focus-within) .pick-details {{ display: block; }}
    .today-bet:has(.today-pick-line.is-compact:is(:hover, :focus-within)) {{ position: relative; z-index: 4; }}
    .today-pick:has(.team-logo-tip:hover) {{ overflow: visible; position: relative; z-index: 2; }}
    .today-bet:has(.team-logo-tip:hover) {{ position: relative; z-index: 3; }}
    .team-logo-tip {{ position: relative; display: inline-block; line-height: 0; vertical-align: middle; }}
    .team-logo-tip:hover::after {{ content: attr(data-name); position: absolute; left: 50%; bottom: calc(100% + 6px); transform: translateX(-50%); z-index: 5; padding: 2px 6px; border-radius: 4px; background: #111827; color: #f8fafc; font-size: 11px; font-weight: 600; line-height: 1.4; letter-spacing: 0; white-space: nowrap; pointer-events: none; box-shadow: 0 6px 16px rgba(0,0,0,0.35); }}
    .today-pick .team-logo {{ display: inline-block; width: 22px; height: 22px; margin: 0 1px; object-fit: contain; vertical-align: middle; background: transparent; }}
    .today-meta {{ display: flex; align-items: center; flex-wrap: wrap; gap: 5px 8px; color: var(--muted); font-size: 11px; }}
    .today-meta:empty {{ display: none; }}
    .today-when {{ display: flex; align-items: baseline; min-width: 0; gap: 5px; }}
    .today-broadcast-separator {{ color: var(--muted); opacity: 0.6; font-size: 9px; }}
    .today-broadcast {{ position: relative; display: inline-block; width: 40px; height: 10px; line-height: 10px; vertical-align: baseline; color: var(--muted); font-size: 9px; font-weight: 400; white-space: nowrap; }}
    .today-network-logo {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); display: block; width: 40px; height: 18px; object-fit: contain; }}
    .today-network-logo[src$="ESPN-PNG-File.png"] {{ width: 46px; height: 26px; }}
    .today-bet-money .today-start {{ color: inherit; font: inherit; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; white-space: nowrap; }}
    .today-bet-money .today-start.is-live {{ color: var(--bad); }}
    .today-odds {{ flex-shrink: 0; white-space: nowrap; }}
    .today-odds strong {{ color: #b5d3fa; font-size: var(--pick-font-size); font-weight: 700; font-variant-numeric: tabular-nums; }}
    .today-bet .badge-logo {{ width: 18px; height: 18px; border-radius: 5px; }}
    .today-logos .badge-logo {{ background: transparent; border: 0; filter: saturate(0.65); }}
    .today-logos:hover .badge-logo {{ filter: none; }}
    .today-bet-money {{ display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 8px; margin: 0; padding-top: 5px; color: var(--muted); font-size: 11px; font-weight: 400; line-height: 1.4; }}
    .today-panel .today-bet-money dt {{ font-size: 10px; }}
    .today-stake {{ padding: 2px 0; }}
    .today-stake dt {{ color: var(--muted); font-weight: 400; }}
    .today-stake dd {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 3px 6px; }}
    .today-risk-amount {{ --risk-tint: rgba(var(--risk-rgb, 157,176,208),var(--risk-alpha, 0.04)); color: rgb(var(--risk-rgb, 157,176,208)); font-weight: 650; border-radius: 3px; background: var(--risk-tint); box-shadow: 0 0 0 2px var(--risk-tint); }}
    .today-risk-amount[title] {{ cursor: help; }}
    .today-return {{ padding: 5px 0; text-align: right; }}
    .today-return dd {{ font-size: 16px; }}
    .today-net-label {{ position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }}
    .today-panel[data-view="cards"] .today-bet {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; align-content: start; gap: 6px 10px; padding: 10px; }}
    .today-panel[data-view="cards"] .today-bet-top {{ display: contents; }}
    .today-panel[data-view="cards"] .today-bet-body {{ grid-column: 1; grid-row: 1; padding: 0; }}
    .today-panel[data-view="cards"] .today-logos {{ grid-column: 2; grid-row: 1; align-self: start; gap: 4px; max-width: 84px; margin-top: 2px; }}
    .today-panel[data-view="cards"] .today-league {{ grid-column: 1 / -1; }}
    .today-panel[data-view="cards"] .today-pick-line {{ min-height: 22px; align-items: center; }}
    .today-panel[data-view="cards"] .today-pick {{ margin: 0; min-width: 0; }}
    .today-panel[data-view="cards"] .today-meta {{ gap: 4px 6px; margin-top: 4px; line-height: 1.4; }}
    .today-panel[data-view="cards"] .today-bet-money {{ grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 8px; margin-top: 2px; padding-top: 7px; border-top: 1px solid rgba(255,255,255,0.055); }}
    .today-panel[data-view="cards"] .today-stake, .today-panel[data-view="cards"] .today-return, .today-panel[data-view="cards"] .today-when {{ display: flex; align-items: baseline; flex-wrap: nowrap; gap: 4px; padding: 0; white-space: nowrap; }}
    .today-panel[data-view="cards"] .today-return {{ margin-left: 0; padding-right: 0; }}
    .today-panel[data-view="cards"] .today-bet-money dd {{ flex-wrap: nowrap; gap: 4px; margin: 0; font-size: 11px; font-weight: 400; }}
    .today-bet-money .today-return dd:not(.positive):not(.negative) {{ color: var(--muted); }}
    .today-empty {{ margin: 0; padding: 12px; text-align: center; color: var(--muted); font-size: 12px; }}
    .today-panel[data-view="list"] .today-bets {{ grid-template-columns: 1fr; gap: 4px; }}
    .today-panel[data-view="list"] .today-bet {{ display: grid; grid-template-columns: max-content minmax(0, 1fr) minmax(240px, 34%) minmax(40px, 84px); align-items: center; gap: 8px; padding: 4px 7px; border-radius: 6px; }}
    .today-panel[data-view="list"] .today-bet-top {{ display: contents; }}
    .today-panel[data-view="list"] .today-league {{ grid-column: 1; grid-row: 1; gap: 5px; }}
    .today-panel[data-view="list"] .today-logos {{ grid-column: 4; grid-row: 1; }}
    .today-panel[data-view="list"] .today-result {{ gap: 3px; }}
    .today-panel[data-view="list"] .today-bet-body {{ grid-column: 2; grid-row: 1; padding: 0; }}
    .today-panel[data-view="list"] .today-bet--open .today-bet-body {{ grid-column: 1 / 3; }}
    .today-panel[data-view="list"] .today-meta {{ gap: 3px 6px; }}
    .today-panel[data-view="list"] .badge-logo {{ width: 16px; height: 16px; padding: 0; border-radius: 4px; }}
    .today-panel[data-view="list"] .today-bet-money {{ grid-column: 3; grid-row: 1; display: flex; align-items: baseline; flex-wrap: wrap; justify-content: space-between; gap: 3px 0; border-left: 1px solid rgba(255,255,255,0.055); padding: 0 0 0 8px; }}
    .today-panel[data-view="list"] .today-bet-money > * + *::before {{ content: "|"; margin-right: 8px; color: var(--muted); font-weight: 400; }}
    .today-panel[data-view="list"] .today-stake, .today-panel[data-view="list"] .today-return, .today-panel[data-view="list"] .today-when {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 3px 5px; padding: 0; }}
    .today-panel[data-view="list"] .today-return {{ margin-left: 0; padding-right: 0; }}
    .today-panel[data-view="list"] .today-bet-money dd {{ margin: 0; font-size: 11px; font-weight: 400; }}
    @media (max-width: 1100px) {{
      .today-bets {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .today-panel[data-view="list"] .today-bet {{ grid-template-columns: max-content minmax(0, 1fr) minmax(220px, 36%) minmax(40px, 84px); gap: 6px; }}
    }}
    @media (max-width: 850px) {{
      .today-bets {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .today-bets {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 720px) {{
      .today-summary {{ order: 1; flex-basis: 100%; margin-left: 0; }}
      .today-panel[data-view="list"] .today-bet {{ grid-template-columns: minmax(0, 1fr) auto; gap: 4px; }}
      .today-panel[data-view="list"] .today-logos {{ grid-column: 2; align-self: start; max-width: 84px; }}
      .today-panel[data-view="list"] .today-bet .today-bet-body {{ grid-column: 1; grid-row: 1; }}
      .today-panel[data-view="list"] .today-league {{ grid-column: 1 / -1; grid-row: auto; }}
      .today-panel[data-view="list"] .today-bet-money {{ grid-column: 1 / -1; grid-row: auto; margin-top: 6px; padding: 2px 0 0; border-left: 0; border-top: 1px solid rgba(255,255,255,0.055); }}
    }}

    @media (max-width: 1000px) {{
      .kpi {{ grid-column: span 6; }}
      .half {{ grid-column: span 12; }}
      .third {{ grid-column: span 12; }}
      .history-split {{ grid-template-columns: 1fr; }}
      .filter-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .all-bets-kpis {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .filter-grid {{ grid-template-columns: 1fr; }}
      .filter-range {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>{html.escape(title)}</h1>
    <div class=\"subtitle\">As of {html.escape(as_of)} | Last synced {html.escape(last_synced)}</div>
    <div class="tabs">
      <button class="tab-btn active" data-tab="home">Home</button>
      <button class="tab-btn" data-tab="history">History</button>
      <button class="tab-btn" data-tab="all-bets">All Bets</button>
      <button class="tab-btn" data-tab="sports">Sports</button>
    </div>

    <section id="tab-home" class="tab-panel active">
      <div class=\"grid\">
        <div class="card kpi">
          <div class="label">Total Bets</div>
          <div class="value">{counts['total']}</div>
          <div class="note">{_record_note(counts)}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Net Profit</div>
          <div class=\"value {'good' if totals['net'] >= 0 else 'bad'}\">{_fmt_money(totals['net'])}</div>
          <div class=\"note\">Settled ROI: {_fmt_pct(totals['roi'])}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Win Rate (W/L only)</div>
          <div class=\"value\">{_fmt_pct(avgs['win_rate'])}</div>
          <div class=\"note\">W: {counts['wins']} | L: {counts['losses']} | Edge vs implied: {_fmt_edge(avgs['edge'])}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Open Risk</div>
          <div class=\"value\">{_fmt_money(summary['open_exposure'])}</div>
        </div>

        <section id="today-panel" class="card full today-panel" data-view="cards" aria-labelledby="today-title">
          <div class="today-header">
            <div>
              <div class="today-heading"><h2 id="today-title">Today</h2><span class="today-date">{today_label}</span></div>
              <div id="today-wager-count" class="note">{len(today_rows)} wagers · {len(summary['today_open'])} open · {len(summary['today_settled'])} settled</div>
            </div>
          <dl class="today-summary">
            <div data-today-total="risk"><dt>Total risk</dt><dd>{_fmt_money_compact(today_risk_total)}</dd></div>
            <div data-today-total="open"><dt>Open risk</dt><dd class="today-risk-value">{_fmt_money_compact(today_open_risk)}</dd></div>
            <div data-today-total="net"><dt>Settled net</dt><dd class="{_net_class(today_net_total)}">{_fmt_money_compact(today_net_total)}</dd></div>
          </dl>
            {bet_view_controls("today", "Today’s bet layout")}
          </div>
          {bet_cards(today_rows)}
        </section>

        <section id="upcoming-panel" class="card full today-panel" data-view="cards" aria-labelledby="upcoming-title">
          <div class="today-header">
            <div>
              <div class="today-heading"><h2 id="upcoming-title">Upcoming Open Bets</h2></div>
              <div id="upcoming-wager-count" class="note">{len(summary['future_open'])} open wagers · After {today_label}</div>
            </div>
            <dl class="today-summary">
              <div data-today-total="open"><dt>Open risk</dt><dd class="today-risk-value">{_fmt_money_compact(_sum_finite(r.get('risk') for r in summary['future_open']))}</dd></div>
              <div data-today-total="potential"><dt>wins</dt><dd>{_fmt_money_compact(_sum_finite(r.get('to_win') for r in summary['future_open']))}</dd></div>
            </dl>
            {bet_view_controls("upcoming", "Upcoming bet layout")}
          </div>
          {bet_cards(summary['future_open'], "upcoming")}
        </section>

        <div class="card full">
          <div class="section-title">Daily Net / Risk (Last 7 Days)</div>
          {daily_net_risk_calendar(summary['recent_7_day_calendar'])}
        </div>

        <div class="card full">
          <div class="section-title">Recent Performance</div>
          <div class="note">Net and ROI use settled bets only. Open stakes stay in Open Risk.</div>
          <div class="scroll">{period_table(summary['recent_periods'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">Recently Settled Bets</div>
          <div class="scroll">{bets_table(summary['recently_settled'][:25])}</div>
        </div>

        <div class="card half">
          <div class="section-title">Notable Streaks</div>
          <div class="note">{html.escape(daily_current_text)}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            {streak_line("Longest daily win streak", daily_streaks["best_win"])}
            {streak_line("Longest daily loss streak", daily_streaks["best_loss"])}
          </div>
        </div>

        <div class="card half">
          <div class="section-title">Recent Highlights</div>
          <div class="note">Avg Risk / Bet: {_fmt_money(avgs['avg_risk'])}</div>
          <div class="note">{_edge_note(avgs)}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            <div><strong>Best settled day:</strong> {html.escape(best_day['date']) if best_day else 'n/a'} ({_fmt_money(best_day['net']) if best_day else 'n/a'})</div>
            <div><strong>Worst settled day:</strong> {html.escape(worst_day['date']) if worst_day else 'n/a'} ({_fmt_money(worst_day['net']) if worst_day else 'n/a'})</div>
          </div>
        </div>

        <div class="card full">
          <div class="section-title">Last 30 Days Net (daily)</div>
          <div id="chart-recent" style="height: 320px;"></div>
          <div class="note">Includes zero values on days with no bets.</div>
        </div>
      </div>
    </section>

    <section id="tab-history" class="tab-panel">
      <div class=\"grid\">
        <div class="card full">
          <div class="section-title">Cumulative Profit</div>
          <div id="chart-cum" style="height: 360px;"></div>
          <div class="note">Cumulative ROI = settled net / settled risk. Open bets are excluded.</div>
        </div>
      </div>

      <div class="history-split">
        <div class="history-col">
          <div class="card">
            <div class=\"section-title\">By League (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_league'], badge_kind='league')}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">By Type (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_type'])}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Biggest Wins (top 10)</div>
            <div class=\"scroll\">{bets_table(summary['top_wins'], include_result=False)}</div>
          </div>
        </div>
        <div class="history-col">
          <div class="card">
            <div class=\"section-title\">By Book (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_book'], badge_kind='book')}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Biggest Losses (top 10)</div>
            <div class=\"scroll\">{bets_table(summary['top_losses'], include_result=False)}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Longest Shots (top 10 winning odds)</div>
            <div class=\"note\">Winning wagers with the longest pre-game odds (lowest implied win probability).</div>
            <div class=\"scroll\">{bets_table(summary['longest_shots'], include_result=False)}</div>
          </div>
        </div>
      </div>
    </section>

    <section id="tab-all-bets" class="tab-panel">
      <div class="card">
        <div class="section-title">All Bets (2026+)</div>
        <div class="note">Every table column now has a dedicated filter. Use date ranges or numeric min/max for greater-than / less-than filtering.</div>

        <div class="filter-grid">
          <label class="filter-field">
            <span class="filter-label">Pick Contains</span>
            <input id="all-bets-pick-filter" class="control-input" type="text" placeholder="Exact pick text or fragment" />
          </label>
          <label class="filter-field">
            <span class="filter-label">Date Range</span>
            <div class="filter-range">
              <input id="all-bets-date-from" class="control-input" type="date" />
              <input id="all-bets-date-to" class="control-input" type="date" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">League</span>
            <select id="all-bets-league-filter" class="control-input">
              <option value="">All leagues</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Book</span>
            <select id="all-bets-book-filter" class="control-input">
              <option value="">All books</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Type</span>
            <select id="all-bets-type-filter" class="control-input">
              <option value="">All types</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Result</span>
            <select id="all-bets-result-filter" class="control-input">
              <option value="">All results</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Odds Range</span>
            <div class="filter-range">
              <input id="all-bets-odds-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-odds-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">Risk Range</span>
            <div class="filter-range">
              <input id="all-bets-risk-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-risk-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">Net Range</span>
            <div class="filter-range">
              <input id="all-bets-net-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-net-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <div class="filter-actions">
            <button id="all-bets-clear" class="filter-btn" type="button">Clear Filters</button>
          </div>
        </div>

        <div class="all-bets-kpis">
          <div class="sub-kpi">
            <div class="label">Visible Bets</div>
            <div id="all-bets-count" class="value">0</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Visible Risk</div>
            <div id="all-bets-risk" class="value">$0.00</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Visible Net</div>
            <div id="all-bets-net" class="value">$0.00</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Settled ROI</div>
            <div id="all-bets-roi" class="value">0.00%</div>
          </div>
          <div class="sub-kpi">
            <div class="label">W-L-Open</div>
            <div id="all-bets-wlo" class="value">0-0-0</div>
          </div>
        </div>

        {all_bets_table(summary['all_bets'])}
      </div>
    </section>

    <section id="tab-sports" class="tab-panel">
      <div class="row-controls">
        <select id="sport-select" class="control-input">
          {sport_options_html}
        </select>
        <div class="note">Switch this tab to any league tag in your sheet. It starts on {html.escape(default_sport)} to preserve the current workflow.</div>
      </div>
      <div class="grid">
        <div class="card kpi">
          <div id="sport-kpi-total-label" class="label">{html.escape(default_sport_payload['label'])} Total Bets</div>
          <div id="sport-kpi-total-value" class="value">{default_sport_payload['counts']['total']}</div>
          <div id="sport-kpi-total-note" class="note">{_record_note(default_sport_payload['counts'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-net-label" class="label">{html.escape(default_sport_payload['label'])} Net Profit</div>
          <div id="sport-kpi-net-value" class="value {'good' if default_sport_payload['totals']['net'] >= 0 else 'bad'}">{_fmt_money(default_sport_payload['totals']['net'])}</div>
          <div id="sport-kpi-net-note" class="note">Settled ROI: {_fmt_pct(default_sport_payload['totals']['roi'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-win-label" class="label">{html.escape(default_sport_payload['label'])} Win Rate (W/L)</div>
          <div id="sport-kpi-win-value" class="value">{_fmt_pct(default_sport_payload['averages']['win_rate'])}</div>
          <div id="sport-kpi-win-note" class="note">W: {default_sport_payload['counts']['wins']} | L: {default_sport_payload['counts']['losses']} | Edge vs implied: {_fmt_edge(default_sport_payload['averages']['edge'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-open-label" class="label">{html.escape(default_sport_payload['label'])} Open Exposure</div>
          <div id="sport-kpi-open-value" class="value">{_fmt_money(default_sport_payload['open_exposure'])}</div>
          <div id="sport-kpi-open-note" class="note">As of {html.escape(default_sport_payload['as_of'])} | League tag = <code>{html.escape(default_sport_payload['label'])}</code></div>
        </div>

        <div class="card full">
          <div id="sport-periods-title" class="section-title">{html.escape(default_sport_payload['label'])} Recent Performance</div>
          <div id="sport-periods-note" class="note">Calendar-day windows ending on {html.escape(default_sport_payload['as_of'])}. Net and ROI use settled bets only.</div>
          <div id="sport-periods-table" class="scroll">{default_sport_payload['recent_periods_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-calendar-title" class="section-title">{html.escape(default_sport_payload['label'])} Daily Net / Risk (Last 7 Days)</div>
          <div id="sport-calendar-content">{default_sport_payload['recent_calendar_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-streaks-title" class="section-title">{html.escape(default_sport_payload['label'])} Notable Streaks</div>
          <div id="sport-daily-streak-note" class="note">{html.escape(default_sport_payload['daily_current_text'])}</div>
          <div id="sport-streak-lines" style="margin-top: 8px; line-height: 1.6;">{default_sport_payload['streak_lines_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-highlights-title" class="section-title">{html.escape(default_sport_payload['label'])} Highlights</div>
          <div id="sport-highlights-risk" class="note">Avg Risk / Bet: {_fmt_money(default_sport_payload['averages']['avg_risk'])}</div>
          <div id="sport-highlights-odds" class="note">{_edge_note(default_sport_payload['averages'])}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            <div><strong>Best settled day:</strong> <span id="sport-best-day">{html.escape(default_sport_payload['best_day_text'])}</span></div>
            <div><strong>Worst settled day:</strong> <span id="sport-worst-day">{html.escape(default_sport_payload['worst_day_text'])}</span></div>
          </div>
        </div>

        <div class="card full">
          <div id="sport-cum-title" class="section-title">{html.escape(default_sport_payload['label'])} Cumulative Profit</div>
          <div id="chart-cum-sport" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div id="sport-recent-title" class="section-title">{html.escape(default_sport_payload['label'])} Last 30 Days Net (daily)</div>
          <div id="chart-recent-sport" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div id="sport-settled-title" class="section-title">{html.escape(default_sport_payload['label'])} Recently Settled Bets</div>
          <div class="note">Most recent settled bets, latest 25.</div>
          <div id="sport-settled-table" class="scroll">{default_sport_payload['recently_settled_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-open-title" class="section-title">{html.escape(default_sport_payload['label'])} Open Bets</div>
          <div id="sport-open-note" class="note">Open bets tagged with League <code>{html.escape(default_sport_payload['label'])}</code>.</div>
          <div id="sport-open-table" class="scroll">{default_sport_payload['open_bets_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-by-book-title" class="section-title">{html.escape(default_sport_payload['label'])} By Book</div>
          <div id="sport-by-book-table" class="scroll">{default_sport_payload['by_book_html']}</div>
        </div>
        <div class="card half">
          <div id="sport-by-type-title" class="section-title">{html.escape(default_sport_payload['label'])} By Type</div>
          <div id="sport-by-type-table" class="scroll">{default_sport_payload['by_type_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-wins-title" class="section-title">{html.escape(default_sport_payload['label'])} Biggest Wins (top 10)</div>
          <div id="sport-wins-table" class="scroll">{default_sport_payload['top_wins_html']}</div>
        </div>
        <div class="card half">
          <div id="sport-losses-title" class="section-title">{html.escape(default_sport_payload['label'])} Biggest Losses (top 10)</div>
          <div id="sport-losses-table" class="scroll">{default_sport_payload['top_losses_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-longest-title" class="section-title">{html.escape(default_sport_payload['label'])} Longest Shots (top 10 winning odds)</div>
          <div id="sport-longest-table" class="scroll">{default_sport_payload['longest_shots_html']}</div>
        </div>
      </div>
    </section>
  </div>

<script>
  // Fit each pick and its odds on one line without increasing the card height.
  // Long parlays use a readable summary with full details on hover or focus.
  function fitPickLine(line, width) {{
    const maxSize = 13, minSize = 10, gap = 6;
    line.style.setProperty('--pick-font-size', `${{maxSize}}px`);
    const pick = line.querySelector('.today-pick');
    const odds = line.querySelector('.today-odds');
    const compact = line.querySelector('.compact-pick');
    if (compact) {{
      pick.hidden = false;
      compact.hidden = true;
      line.classList.remove('is-compact');
      const range = document.createRange();
      range.selectNodeContents(pick);
      const fits = () => range.getBoundingClientRect().width + odds.getBoundingClientRect().width <= width - gap;
      if (fits()) return;
      const comfortableSize = 11;
      line.style.setProperty('--pick-font-size', `${{comfortableSize}}px`);
      if (!fits()) {{
        pick.hidden = true;
        compact.hidden = false;
        line.classList.add('is-compact');
        line.style.setProperty('--pick-font-size', `${{maxSize}}px`);
        return;
      }}
      let lower = comfortableSize, upper = maxSize;
      for (let step = 0; step < 8; step++) {{
        const size = (lower + upper) / 2;
        line.style.setProperty('--pick-font-size', `${{size}}px`);
        if (fits()) lower = size;
        else upper = size;
      }}
      line.style.setProperty('--pick-font-size', `${{lower}}px`);
      return;
    }}
    const textWidth = pick.scrollWidth + odds.getBoundingClientRect().width;
    if (textWidth > width - gap) {{
      const size = Math.max(minSize, Math.floor(maxSize * Math.max(0, width - gap) / textWidth * 4) / 4);
      line.style.setProperty('--pick-font-size', `${{size}}px`);
    }}
  }}
  document.querySelectorAll('.compact-pick').forEach(button => {{
    const line = button.closest('.today-pick-line');
    line.addEventListener('mouseenter', () => line.classList.remove('details-dismissed'));
    button.addEventListener('focus', () => line.classList.remove('details-dismissed'));
    button.addEventListener('click', () => {{ line.classList.remove('details-dismissed'); button.focus(); }});
    line.addEventListener('keydown', event => {{
      if (event.key === 'Escape') line.classList.add('details-dismissed');
    }});
  }});
  if (typeof ResizeObserver !== 'undefined') {{
    const fittedWidths = new WeakMap();
    const pickObserver = new ResizeObserver(entries => {{
      entries.forEach(entry => {{
        const width = entry.contentRect.width;
        if (width <= 0 || fittedWidths.get(entry.target) === width) return;
        fittedWidths.set(entry.target, width);
        fitPickLine(entry.target, width);
      }});
    }});
    document.querySelectorAll('.today-pick-line').forEach(line => pickObserver.observe(line));
  }}

  // The pick line title covers the logo and would hide its team-name label.
  // Lift that title while the pointer is on a logo.
  document.querySelectorAll('.team-logo').forEach(logo => {{
    const line = logo.closest('.today-pick-line');
    if (!line) return;
    logo.addEventListener('mouseenter', () => {{
      logo.dataset.lineTitle = line.getAttribute('title') || '';
      line.removeAttribute('title');
    }});
    logo.addEventListener('mouseleave', () => {{
      const saved = logo.dataset.lineTitle;
      if (saved) line.setAttribute('title', saved);
      else line.removeAttribute('title');
    }});
  }});

  // Keep the layout control independent of chart loading and browser storage access.
  document.querySelectorAll('.today-panel').forEach(panel => {{
    const panelKey = panel.id.replace('-panel', '');
    const upcoming = panelKey === 'upcoming';
    const storageKey = upcoming ? 'bettingReportUpcomingView' : 'bettingReportTodayView';
    const controls = panel.querySelector('.today-view');
    const buttons = panel.querySelectorAll('[data-today-view]');
    const setView = view => {{
      const selected = view === 'list' ? 'list' : 'cards';
      panel.dataset.view = selected;
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todayView === selected)));
    }};
    try {{ setView(localStorage.getItem(storageKey)); }} catch {{ setView('cards'); }}
    if (panel.querySelector(`#${{panelKey}}-bets`)) controls.hidden = false;
    buttons.forEach(button => button.addEventListener('click', () => {{
      setView(button.dataset.todayView);
      try {{ localStorage.setItem(storageKey, panel.dataset.view); }} catch {{ /* Layout still works without storage. */ }}
    }}));
    const filterBar = panel.querySelector('.today-filter-bar');
    if (!filterBar) return;
    const leagueButtons = panel.querySelectorAll('[data-today-league]');
    const groups = panel.querySelectorAll('[data-today-group]');
    const bets = Array.from(panel.querySelectorAll('.today-bet'));
    const sortButtons = panel.querySelectorAll('[data-today-sort]');
    const sortStorageKey = upcoming ? 'bettingReportUpcomingSort' : 'bettingReportTodaySort';
    const originalOrder = new Map(bets.map((bet, index) => [bet, index]));
    const startTime = bet => bet.dataset.startMs ? Number(bet.dataset.startMs) : Infinity;
    const setSort = value => {{
      const selected = value === 'risk' ? 'risk' : 'time';
      panel.dataset.sort = selected;
      sortButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todaySort === selected)));
      panel.querySelectorAll('.today-bets').forEach(list => {{
        const sorted = Array.from(list.children).sort((a, b) => {{
          const timeDifference = startTime(a) - startTime(b);
          const riskDifference = Number(b.dataset.risk) - Number(a.dataset.risk);
          return (selected === 'risk' ? riskDifference || timeDifference : timeDifference || riskDifference)
            || originalOrder.get(a) - originalOrder.get(b);
        }});
        list.append(...sorted);
      }});
    }};
    try {{ setSort(localStorage.getItem(sortStorageKey)); }} catch {{ setSort('time'); }}
    sortButtons.forEach(button => button.addEventListener('click', () => {{
      setSort(button.dataset.todaySort);
      try {{ localStorage.setItem(sortStorageKey, panel.dataset.sort); }} catch {{ /* Sorting still works without storage. */ }}
    }}));
    let league = '';
    const money = value => '$' + value.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}).replace(/[.]00$/, '');
    const applyFilters = () => {{
      let risk = 0, openRisk = 0, net = 0, potential = 0, wagers = 0, open = 0, visible = 0;
      bets.forEach(bet => {{
        bet.hidden = Boolean(league && bet.dataset.league !== league);
        if (bet.hidden) return;
        visible++;
        const stake = Number(bet.dataset.risk);
        const count = Number(bet.dataset.count);
        risk += stake;
        net += Number(bet.dataset.net);
        potential += Number(bet.dataset.potential);
        wagers += count;
        if (bet.dataset.open === 'true') {{ openRisk += stake; open += count; }}
      }});
      leagueButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todayLeague === league)));
      panel.querySelectorAll('[data-bet-section]').forEach(section => {{
        section.hidden = !section.querySelector('.today-bet:not([hidden])');
      }});
      groups.forEach(group => {{
        const count = Array.from(group.querySelectorAll('.today-bet')).filter(bet => !bet.hidden).length;
        group.hidden = count === 0;
        group.querySelector('.today-group-count').textContent = count;
      }});
      panel.querySelector(`#${{panelKey}}-filter-empty`).hidden = visible > 0;
      Object.entries({{risk, open: openRisk, potential, net}}).forEach(([key, value]) => {{
        const total = panel.querySelector(`[data-today-total="${{key}}"] dd`);
        if (total) total.textContent = money(value);
      }});
      const netValue = panel.querySelector('[data-today-total="net"] dd');
      if (netValue) netValue.className = net > 0 ? 'positive' : net < 0 ? 'negative' : '';
      panel.querySelector(`#${{panelKey}}-wager-count`).textContent = upcoming
        ? `${{wagers}} open wagers · After {today_label}`
        : `${{wagers}} wagers · ${{open}} open · ${{wagers - open}} settled`;
      panel.querySelector(`#${{panelKey}}-filter-count`).textContent = `${{league || 'All leagues'}} · ${{visible}} of ${{bets.length}} bets`;
    }};
    leagueButtons.forEach(button => button.addEventListener('click', () => {{ league = button.dataset.todayLeague; applyFilters(); }}));
    applyFilters();
    filterBar.hidden = false;
  }});

  const series = {series_json};
  const recentSeries = {recent_series_json};
  const sportSummaries = {sport_summaries_json};
  const defaultSport = {json.dumps(default_sport)};

  const x = series.map(d => d.date);
  const yCum = series.map(d => d.cum_net);
  const yDaily = series.map(d => d.net);
  const yCumRoi = series.map(d => d.cum_roi == null ? null : d.cum_roi * 100.0);

  const traceCum = {{
    x, y: yCum, type: 'scatter', mode: 'lines+markers', name: 'Cumulative Net',
    line: {{ color: '#60a5fa', width: 3 }},
    hovertemplate: '%{{x}}<br>Cumulative Net: %{{y:$,.2f}}<extra></extra>'
  }};

  const traceDaily = {{
    x, y: yDaily, type: 'bar', name: 'Daily Net',
    marker: {{ color: yDaily.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    opacity: 0.55,
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};

  const traceCumRoi = {{
    x, y: yCumRoi, type: 'scatter', mode: 'lines', name: 'Cumulative ROI %',
    yaxis: 'y2',
    line: {{ color: 'rgba(157,176,208,0.9)', width: 2, dash: 'dot' }},
    hovertemplate: '%{{x}}<br>Cumulative ROI: %{{y:.2f}}%<extra></extra>'
  }};

  const layout = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {{ color: '#e6eefc' }},
    margin: {{ l: 55, r: 55, t: 10, b: 45 }},
    legend: {{ orientation: 'h', y: 1.15, x: 0 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis: {{ title: 'Net ($)', gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis2: {{ title: 'ROI (%)', overlaying: 'y', side: 'right', showgrid: false }},
    barmode: 'overlay'
  }};

  Plotly.newPlot('chart-cum', [traceDaily, traceCum, traceCumRoi], layout, {{displayModeBar: false, responsive: true}});

  const recentX = recentSeries.map(d => d.date);
  const recentY = recentSeries.map(d => d.net);
  const recentTrace = {{
    x: recentX,
    y: recentY,
    type: 'bar',
    marker: {{ color: recentY.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};
  const recentLayout = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {{ color: '#e6eefc' }},
    margin: {{ l: 55, r: 25, t: 10, b: 45 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis: {{ title: 'Net ($)', gridcolor: 'rgba(255,255,255,0.06)' }},
  }};
  Plotly.newPlot('chart-recent', [recentTrace], recentLayout, {{displayModeBar: false, responsive: true}});

  function fmtMoney(value) {{
    const n = Number.isFinite(value) ? value : 0;
    return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}
  function fmtPct(value) {{
    if (!Number.isFinite(value)) return '';
    return (value * 100).toFixed(2) + '%';
  }}
  function fmtEdge(value) {{
    if (!Number.isFinite(value)) return 'n/a';
    const pts = value * 100;
    return (pts > 0 ? '+' : '') + pts.toFixed(2) + ' pts';
  }}
  function resultFilterLabel(value) {{
    if (value === '__OPEN__') return 'Open';
    if (value === 'CO') return 'Cash Out';
    return value;
  }}
  function fmtNum(value) {{
    if (!Number.isFinite(value)) return '';
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }}
  function escapeHtml(value) {{
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }}
  function normalizeText(value) {{
    return String(value || '').trim().toLowerCase();
  }}
  function parseNum(row, key) {{
    const v = Number.parseFloat((row.dataset[key] || '').trim());
    return Number.isFinite(v) ? v : NaN;
  }}
  function parseOptionalNumberInput(input) {{
    const raw = (input?.value || '').trim();
    if (!raw) return null;
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }}
  function matchesRange(value, minValue, maxValue) {{
    if (minValue == null && maxValue == null) return true;
    if (!Number.isFinite(value)) return false;
    if (minValue != null && value < minValue) return false;
    if (maxValue != null && value > maxValue) return false;
    return true;
  }}
  function setSignedClass(el, value) {{
    if (!el) return;
    el.classList.remove('positive', 'negative', 'good', 'bad');
    if (value > 0) el.classList.add('positive');
    else if (value < 0) el.classList.add('negative');
  }}
  function setText(id, value) {{
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }}
  function setHtml(id, value) {{
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
  }}
  function buildSportCumulativeTraces(seriesData, label) {{
    const sportX = seriesData.map(d => d.date);
    const sportYCum = seriesData.map(d => d.cum_net);
    const sportYDaily = seriesData.map(d => d.net);
    const sportYCumRoi = seriesData.map(d => d.cum_roi == null ? null : d.cum_roi * 100.0);
    return [
      {{
        x: sportX,
        y: sportYDaily,
        type: 'bar',
        name: `${{label}} Daily Net`,
        marker: {{ color: sportYDaily.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
        opacity: 0.55,
        hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
      }},
      {{
        x: sportX,
        y: sportYCum,
        type: 'scatter',
        mode: 'lines+markers',
        name: `${{label}} Cumulative Net`,
        line: {{ color: '#60a5fa', width: 3 }},
        hovertemplate: '%{{x}}<br>Cumulative Net: %{{y:$,.2f}}<extra></extra>'
      }},
      {{
        x: sportX,
        y: sportYCumRoi,
        type: 'scatter',
        mode: 'lines',
        name: `${{label}} Cumulative ROI %`,
        yaxis: 'y2',
        line: {{ color: 'rgba(157,176,208,0.9)', width: 2, dash: 'dot' }},
        hovertemplate: '%{{x}}<br>Cumulative ROI: %{{y:.2f}}%<extra></extra>'
      }},
    ];
  }}
  function buildSportRecentTrace(seriesData) {{
    const sportRecentX = seriesData.map(d => d.date);
    const sportRecentY = seriesData.map(d => d.net);
    return {{
      x: sportRecentX,
      y: sportRecentY,
      type: 'bar',
      marker: {{ color: sportRecentY.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
      hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
    }};
  }}
  function renderSportTab(sportKey) {{
    const sport = sportSummaries[sportKey] || sportSummaries[defaultSport];
    if (!sport) return;

    setText('sport-kpi-total-label', `${{sport.label}} Total Bets`);
    setText('sport-kpi-total-value', String(sport.counts.total));
    setText('sport-kpi-total-note', `Resolved: ${{sport.counts.resolved}} | Open: ${{sport.counts.open}} | Push: ${{sport.counts.pushes}} | Cash out: ${{sport.counts.cash_outs}}`);

    setText('sport-kpi-net-label', `${{sport.label}} Net Profit`);
    setText('sport-kpi-net-value', fmtMoney(sport.totals.net));
    setText('sport-kpi-net-note', `Settled ROI: ${{fmtPct(sport.totals.roi)}}`);
    setSignedClass(document.getElementById('sport-kpi-net-value'), sport.totals.net);

    setText('sport-kpi-win-label', `${{sport.label}} Win Rate (W/L)`);
    setText('sport-kpi-win-value', fmtPct(sport.averages.win_rate));
    setText('sport-kpi-win-note', `W: ${{sport.counts.wins}} | L: ${{sport.counts.losses}} | Edge vs implied: ${{fmtEdge(sport.averages.edge)}}`);

    setText('sport-kpi-open-label', `${{sport.label}} Open Exposure`);
    setText('sport-kpi-open-value', fmtMoney(sport.open_exposure));
    setHtml('sport-kpi-open-note', `As of ${{escapeHtml(sport.as_of)}} | League tag = <code>${{escapeHtml(sport.label)}}</code>`);

    setText('sport-periods-title', `${{sport.label}} Recent Performance`);
    setText('sport-periods-note', `Calendar-day windows ending on ${{sport.as_of}}. Net and ROI use settled bets only.`);
    setHtml('sport-periods-table', sport.recent_periods_html);

    setText('sport-calendar-title', `${{sport.label}} Daily Net / Risk (Last 7 Days)`);
    setHtml('sport-calendar-content', sport.recent_calendar_html);

    setText('sport-streaks-title', `${{sport.label}} Notable Streaks`);
    setText('sport-daily-streak-note', sport.daily_current_text);
    setHtml('sport-streak-lines', sport.streak_lines_html);

    setText('sport-highlights-title', `${{sport.label}} Highlights`);
    setText('sport-highlights-risk', `Avg Risk / Bet: ${{fmtMoney(sport.averages.avg_risk)}}`);
    setText('sport-highlights-odds', `Win ${{fmtPct(sport.averages.win_rate) || 'n/a'}} vs implied ${{fmtPct(sport.averages.avg_implied_prob) || 'n/a'}} (edge ${{fmtEdge(sport.averages.edge)}})`);
    setText('sport-best-day', sport.best_day_text);
    setText('sport-worst-day', sport.worst_day_text);

    setText('sport-cum-title', `${{sport.label}} Cumulative Profit`);
    setText('sport-recent-title', `${{sport.label}} Last 30 Days Net (daily)`);
    setText('sport-settled-title', `${{sport.label}} Recently Settled Bets`);
    setHtml('sport-settled-table', sport.recently_settled_html);

    setText('sport-open-title', `${{sport.label}} Open Bets`);
    setHtml('sport-open-note', `Open bets tagged with League <code>${{escapeHtml(sport.label)}}</code>.`);
    setHtml('sport-open-table', sport.open_bets_html);

    setText('sport-by-book-title', `${{sport.label}} By Book`);
    setHtml('sport-by-book-table', sport.by_book_html);
    setText('sport-by-type-title', `${{sport.label}} By Type`);
    setHtml('sport-by-type-table', sport.by_type_html);

    setText('sport-wins-title', `${{sport.label}} Biggest Wins (top 10)`);
    setHtml('sport-wins-table', sport.top_wins_html);
    setText('sport-losses-title', `${{sport.label}} Biggest Losses (top 10)`);
    setHtml('sport-losses-table', sport.top_losses_html);
    setText('sport-longest-title', `${{sport.label}} Longest Shots (top 10 winning odds)`);
    setHtml('sport-longest-table', sport.longest_shots_html);

    const sportCumChart = document.getElementById('chart-cum-sport');
    const sportRecentChart = document.getElementById('chart-recent-sport');
    if (sportCumChart) {{
      Plotly.react(sportCumChart, buildSportCumulativeTraces(sport.series, sport.label), layout, {{displayModeBar: false, responsive: true}});
    }}
    if (sportRecentChart) {{
      Plotly.react(sportRecentChart, [buildSportRecentTrace(sport.recent_daily_series)], recentLayout, {{displayModeBar: false, responsive: true}});
    }}

    const sportSelect = document.getElementById('sport-select');
    if (sportSelect && sportSelect.value !== sportKey) {{
      sportSelect.value = sportKey;
    }}
    localStorage.setItem('bettingReportSelectedSport', sportKey);
  }}

  const allBetsTable = document.getElementById('all-bets-table');
  const allBetsTbody = allBetsTable ? allBetsTable.querySelector('tbody') : null;
  const allBetsSortButtons = allBetsTable ? Array.from(allBetsTable.querySelectorAll('.sort-btn')) : [];
  const allBetsRows = allBetsTbody ? Array.from(allBetsTbody.querySelectorAll('tr.all-bets-row')) : [];
  const allBetsFilterInputs = {{
    pick: document.getElementById('all-bets-pick-filter'),
    dateFrom: document.getElementById('all-bets-date-from'),
    dateTo: document.getElementById('all-bets-date-to'),
    league: document.getElementById('all-bets-league-filter'),
    book: document.getElementById('all-bets-book-filter'),
    type: document.getElementById('all-bets-type-filter'),
    result: document.getElementById('all-bets-result-filter'),
    oddsMin: document.getElementById('all-bets-odds-min'),
    oddsMax: document.getElementById('all-bets-odds-max'),
    riskMin: document.getElementById('all-bets-risk-min'),
    riskMax: document.getElementById('all-bets-risk-max'),
    netMin: document.getElementById('all-bets-net-min'),
    netMax: document.getElementById('all-bets-net-max'),
  }};
  const allBetsClear = document.getElementById('all-bets-clear');
  const allBetsState = {{ key: 'date', dir: 'desc', type: 'text' }};

  function uniqueValuesFor(key) {{
    const values = new Set();
    allBetsRows.forEach((row) => {{
      const value = (row.dataset[key] || '').trim();
      if (key === 'result' && !value) {{
        values.add('__OPEN__');
      }} else if (value) {{
        values.add(value);
      }}
    }});
    const sorted = Array.from(values);
    sorted.sort((a, b) => {{
      if (a === '__OPEN__') return 1;
      if (b === '__OPEN__') return -1;
      return a.localeCompare(b, undefined, {{ numeric: true, sensitivity: 'base' }});
    }});
    return sorted;
  }}
  function populateSelectOptions(selectEl, values, placeholder) {{
    if (!selectEl) return;
    const currentValue = selectEl.value;
    const options = [`<option value="">${{escapeHtml(placeholder)}}</option>`];
    values.forEach((value) => {{
      const label = resultFilterLabel(value);
      const selected = value === currentValue ? ' selected' : '';
      options.push(`<option value="${{escapeHtml(value)}}"${{selected}}>${{escapeHtml(label)}}</option>`);
    }});
    selectEl.innerHTML = options.join('');
  }}
  function initAllBetsFilters() {{
    populateSelectOptions(allBetsFilterInputs.league, uniqueValuesFor('league'), 'All leagues');
    populateSelectOptions(allBetsFilterInputs.book, uniqueValuesFor('book'), 'All books');
    populateSelectOptions(allBetsFilterInputs.type, uniqueValuesFor('type'), 'All types');
    populateSelectOptions(allBetsFilterInputs.result, uniqueValuesFor('result'), 'All results');
  }}

  function updateAllBetsSortButtons() {{
    allBetsSortButtons.forEach((btn) => {{
      const active = btn.dataset.key === allBetsState.key;
      btn.classList.toggle('active', active);
      let label = btn.textContent.replace(' ↑', '').replace(' ↓', '');
      if (active) {{
        label += allBetsState.dir === 'asc' ? ' ↑' : ' ↓';
      }}
      btn.textContent = label;
    }});
  }}

  function compareAllBetsRows(a, b) {{
    const key = allBetsState.key;
    const dirMul = allBetsState.dir === 'asc' ? 1 : -1;
    if (allBetsState.type === 'number') {{
      const av = parseNum(a, key);
      const bv = parseNum(b, key);
      const an = Number.isFinite(av) ? av : Number.NEGATIVE_INFINITY;
      const bn = Number.isFinite(bv) ? bv : Number.NEGATIVE_INFINITY;
      if (an < bn) return -1 * dirMul;
      if (an > bn) return 1 * dirMul;
      return 0;
    }}
    const at = (a.dataset[key] || '').toLowerCase();
    const bt = (b.dataset[key] || '').toLowerCase();
    return at.localeCompare(bt, undefined, {{ numeric: true, sensitivity: 'base' }}) * dirMul;
  }}

  function updateAllBetsTotals(visibleRows) {{
    const countEl = document.getElementById('all-bets-count');
    const riskEl = document.getElementById('all-bets-risk');
    const netEl = document.getElementById('all-bets-net');
    const roiEl = document.getElementById('all-bets-roi');
    const wloEl = document.getElementById('all-bets-wlo');
    if (!countEl || !riskEl || !netEl || !roiEl || !wloEl) return;

    let risk = 0;
    let settledRisk = 0;
    let net = 0;
    let wins = 0;
    let losses = 0;
    let open = 0;
    visibleRows.forEach((row) => {{
      const result = (row.dataset.result || '').toUpperCase();
      const r = parseNum(row, 'risk');
      const n = parseNum(row, 'net');
      if (Number.isFinite(r)) risk += r;
      if (Number.isFinite(n)) {{
        net += n;
        if (Number.isFinite(r)) settledRisk += r;
      }}
      if (result === 'W') wins += 1;
      else if (result === 'L') losses += 1;
      else if (!result) open += 1;
    }});
    const roi = settledRisk ? (net / settledRisk) : NaN;
    countEl.textContent = String(visibleRows.length);
    riskEl.textContent = fmtMoney(risk);
    netEl.textContent = fmtMoney(net);
    roiEl.textContent = Number.isFinite(roi) ? fmtPct(roi) : 'n/a';
    wloEl.textContent = `${{wins}}-${{losses}}-${{open}}`;
    setSignedClass(netEl, net);
    setSignedClass(roiEl, roi);
  }}

  function rowMatchesAllBetsFilters(row) {{
    const pickQuery = normalizeText(allBetsFilterInputs.pick?.value);
    const dateFrom = (allBetsFilterInputs.dateFrom?.value || '').trim();
    const dateTo = (allBetsFilterInputs.dateTo?.value || '').trim();
    const leagueFilter = normalizeText(allBetsFilterInputs.league?.value);
    const bookFilter = normalizeText(allBetsFilterInputs.book?.value);
    const typeFilter = normalizeText(allBetsFilterInputs.type?.value);
    const resultFilter = (allBetsFilterInputs.result?.value || '').trim();
    const oddsMin = parseOptionalNumberInput(allBetsFilterInputs.oddsMin);
    const oddsMax = parseOptionalNumberInput(allBetsFilterInputs.oddsMax);
    const riskMin = parseOptionalNumberInput(allBetsFilterInputs.riskMin);
    const riskMax = parseOptionalNumberInput(allBetsFilterInputs.riskMax);
    const netMin = parseOptionalNumberInput(allBetsFilterInputs.netMin);
    const netMax = parseOptionalNumberInput(allBetsFilterInputs.netMax);

    if (pickQuery && !normalizeText(row.dataset.pick).includes(pickQuery)) return false;

    const rowDate = (row.dataset.date || '').trim();
    if (dateFrom && (!rowDate || rowDate < dateFrom)) return false;
    if (dateTo && (!rowDate || rowDate > dateTo)) return false;

    if (leagueFilter && normalizeText(row.dataset.league) !== leagueFilter) return false;
    if (bookFilter && normalizeText(row.dataset.book) !== bookFilter) return false;
    if (typeFilter && normalizeText(row.dataset.type) !== typeFilter) return false;

    const rowResult = (row.dataset.result || '').trim();
    if (resultFilter) {{
      if (resultFilter === '__OPEN__') {{
        if (rowResult) return false;
      }} else if (rowResult !== resultFilter) {{
        return false;
      }}
    }}

    if (!matchesRange(parseNum(row, 'odds'), oddsMin, oddsMax)) return false;
    if (!matchesRange(parseNum(row, 'risk'), riskMin, riskMax)) return false;
    if (!matchesRange(parseNum(row, 'net'), netMin, netMax)) return false;
    return true;
  }}

  function applyAllBetsView() {{
    if (!allBetsTbody) return;
    const visibleRows = [];
    const hiddenRows = [];
    allBetsRows.forEach((row) => {{
      const matches = rowMatchesAllBetsFilters(row);
      row.style.display = matches ? '' : 'none';
      if (matches) visibleRows.push(row);
      else hiddenRows.push(row);
    }});

    visibleRows.sort(compareAllBetsRows);
    [...visibleRows, ...hiddenRows].forEach((row) => allBetsTbody.appendChild(row));
    updateAllBetsSortButtons();
    updateAllBetsTotals(visibleRows);
  }}

  Object.values(allBetsFilterInputs).forEach((input) => {{
    if (!input) return;
    const eventName = input.tagName === 'SELECT' ? 'change' : 'input';
    input.addEventListener(eventName, applyAllBetsView);
  }});
  if (allBetsClear) {{
    allBetsClear.addEventListener('click', () => {{
      Object.values(allBetsFilterInputs).forEach((input) => {{
        if (input) input.value = '';
      }});
      applyAllBetsView();
    }});
  }}
  allBetsSortButtons.forEach((btn) => {{
    btn.addEventListener('click', () => {{
      const key = btn.dataset.key || 'date';
      const type = btn.dataset.type || 'text';
      if (allBetsState.key === key) {{
        allBetsState.dir = allBetsState.dir === 'asc' ? 'desc' : 'asc';
      }} else {{
        allBetsState.key = key;
        allBetsState.type = type;
        allBetsState.dir = key === 'date' ? 'desc' : 'asc';
      }}
      applyAllBetsView();
    }});
  }});
  initAllBetsFilters();
  applyAllBetsView();

  const sportSelect = document.getElementById('sport-select');
  if (sportSelect) {{
    sportSelect.addEventListener('change', () => renderSportTab(sportSelect.value || defaultSport));
  }}
  const savedSport = localStorage.getItem('bettingReportSelectedSport');
  renderSportTab(savedSport && sportSummaries[savedSport] ? savedSport : defaultSport);

  const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
  const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));
  function resizeCharts() {{
    const recentChart = document.getElementById('chart-recent');
    const cumulativeChart = document.getElementById('chart-cum');
    const sportRecentChart = document.getElementById('chart-recent-sport');
    const sportCumulativeChart = document.getElementById('chart-cum-sport');
    if (recentChart) Plotly.Plots.resize(recentChart);
    if (cumulativeChart) Plotly.Plots.resize(cumulativeChart);
    if (sportRecentChart) Plotly.Plots.resize(sportRecentChart);
    if (sportCumulativeChart) Plotly.Plots.resize(sportCumulativeChart);
  }}
  function activateTab(tabName) {{
    tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tabName));
    tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${{tabName}}`));
    localStorage.setItem('bettingReportActiveTab', tabName);
    requestAnimationFrame(resizeCharts);
  }}
  tabButtons.forEach((btn) => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));
  const savedTab = localStorage.getItem('bettingReportActiveTab');
  if (savedTab === 'history' || savedTab === 'home' || savedTab === 'sports' || savedTab === 'all-bets') {{
    activateTab(savedTab);
  }} else if (savedTab === 'ncaab') {{
    activateTab('sports');
  }}
  window.addEventListener('resize', resizeCharts);
</script>

</body>
</html>"""

    return html_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an HTML analysis report from bets.csv")
    parser.add_argument("--input", default="bets.csv", help="Path to bets.csv")
    parser.add_argument("--output", default="../index.html", help="Output HTML file")
    parser.add_argument(
        "--sync-url",
        default="",
        help="Optional: published Google Sheet CSV URL to download into --input before generating the report",
    )
    parser.add_argument("--sync-timeout", type=int, default=30, help="HTTP timeout seconds for --sync-url")
    parser.add_argument(
        "--sync-insecure",
        action="store_true",
        help="Disable SSL certificate verification for --sync-url (not recommended)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2025,
        help="Starting year to assume for the first row; year increments when M/D rolls over (e.g. 12/31 -> 1/1)",
    )
    args = parser.parse_args()

    if args.sync_url:
        try:
            data = _download_bytes_with_ssl(
                args.sync_url,
                timeout_seconds=args.sync_timeout,
                insecure=bool(args.sync_insecure),
            )
        except Exception as e:
            raise RuntimeError(
                "Failed to download --sync-url. If this is an SSL certificate issue on macOS, consider installing/updating certifi or rerun with --sync-insecure."
            ) from e
        if not data or b"," not in data:
            raise RuntimeError("Downloaded content does not look like a CSV")
        _atomic_write_bytes(args.input, data)

    bets = read_bets(args.input, start_year=args.start_year)
    # Temporary reporting scope: only include bets from 2026 onward.
    bets = [b for b in bets if b.date >= dt.date(2026, 1, 1)]
    summary = summarize(bets)
    league_groups: Dict[str, List[BetRow]] = {}
    for bet in bets:
        league_key = bet.league.strip().upper()
        if not league_key:
            continue
        league_groups.setdefault(league_key, []).append(bet)
    league_summaries = {league: summarize(rows) for league, rows in sorted(league_groups.items())}
    default_sport = "NCAAB" if "NCAAB" in league_summaries else (next(iter(league_summaries.keys()), "NCAAB"))

    title = "G's Betting Report"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_root = os.path.dirname(script_dir)
    logos_dir = os.path.join(report_root, "logos")
    available_logo_files: Optional[set[str]] = None
    if os.path.isdir(logos_dir):
        available_logo_files = set()
        for dirpath, _, filenames in os.walk(logos_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, logos_dir).replace(os.sep, "/")
                available_logo_files.add(rel.lower())

    out_dir = os.path.dirname(os.path.abspath(args.output))
    logo_base_href = "logos"
    if os.path.isdir(logos_dir):
        logo_base_href = os.path.relpath(logos_dir, out_dir).replace(os.sep, "/")

    card_rows = _collapse_bet_rows(
        summary["today_open"] + summary["today_settled"] + summary["future_open"]
    )
    game_times, game_time_notes = resolve_game_times(card_rows)
    print(f"Game start times attached: {len(game_times)}")
    for (slate_date, league, pick), start in game_times.items():
        print(f"  {slate_date} {league} {pick} -> {start['display']}")
    if game_time_notes:
        print("No start time:")
        for note in game_time_notes:
            print(f"  {note}")

    html_report = build_html_report(
        summary,
        title=title,
        league_summaries=league_summaries,
        default_sport=default_sport,
        logo_base_href=logo_base_href,
        available_logo_files=available_logo_files,
        game_times=game_times,
    )

    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_report)

    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
