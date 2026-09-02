#!/bin/bash
cd "$(dirname "$0")"
echo "Refreshing the attendance dashboard from the CSV files in this folder..."
echo
python3 process.py
echo
echo "----------------------------------------------------------------"
echo "Done. If you saw any WARNING lines above, fix those rows in the"
echo "CSV and run this file again. Otherwise, refresh index.html in"
echo "your browser to see the update."
echo "----------------------------------------------------------------"
read -p "Press Enter to close..."
