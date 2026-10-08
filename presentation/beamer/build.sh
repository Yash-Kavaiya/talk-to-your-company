#!/usr/bin/env bash
# Three passes: counters, progress line and picture overlays all settle by the third.
set -e
for pass in 1 2 3; do pdflatex -interaction=nonstopmode -halt-on-error main.tex > build.out || { grep -n "^!" -A5 main.log | head -20; exit 1; }; done
grep -E "^(Overfull|Underfull \\vbox)" main.log | sort | uniq -c | sort -rn | head -14
rm -f preview/page-*.png; mkdir -p preview; pdftoppm -png -r 80 main.pdf preview/page
