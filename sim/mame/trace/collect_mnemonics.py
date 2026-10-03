import sys, collections, re
c = collections.Counter()
for line in open(sys.argv[1], errors="replace"):
    m = re.match(r"\s*[0-9A-Fa-f]+:\s+([A-Za-z]+)", line)
    if m: c[m.group(1).upper()] += 1
with open(sys.argv[2], "w") as f:
    for k, v in sorted(c.items()): f.write(f"{k} {v}\n")
