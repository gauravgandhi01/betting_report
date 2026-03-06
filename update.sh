/usr/local/bin/python3 /Users/ggandhi001/nhl_tools/betting_report/betting_analysis/generate_bet_report.py \
  --input /Users/ggandhi001/nhl_tools/betting_report/betting_analysis/bets.csv \
  --output /Users/ggandhi001/nhl_tools/betting_report/index.html \
  --start-year 2025 \
  --sync-url 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRWq2b3UQWrMAyMVpvt2ZIfzbIcvF42SOAvx1Q7FtkT3i105w46_K_VoSy_OyBJ1bqs-Ow7n71xlIsa/pub?gid=383914663&single=true&output=csv' \
  >> /Users/ggandhi001/nhl_tools/betting_report/betting_analysis/cron_log.txt 2>&1 && \
cd /Users/ggandhi001/nhl_tools/betting_report && \
/usr/bin/git add -A && \
/usr/bin/git commit -m "Manual Push $(date '+%Y-%m-%d %H:%M')" >> /Users/ggandhi001/nhl_tools/betting_report/betting_analysis/cron_log.txt 2>&1 && \
/usr/bin/git push >> /Users/ggandhi001/nhl_tools/betting_report/betting_analysis/cron_log.txt 2>&1