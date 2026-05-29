import sys, re
text = open('templates/dashboard.html', encoding='utf-8').read()
lines = text.split('\n')
o = 0; c = 0
for i in range(0, 850):
  o += len(re.findall(r'<div', lines[i]))
  c += len(re.findall(r'</div', lines[i]))
  if i >= 835: print(f'Line {i}: open {o}, close {c}, diff {o-c}')
