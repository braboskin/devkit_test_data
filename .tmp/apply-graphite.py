import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\design\mockup-v3.html")
s = p.read_text(encoding="utf-8")
s = s.replace("--island: rgba(26, 30, 37, 0.62);", "--island: rgba(13, 15, 19, 0.62);")
s = s.replace("--island-hi: rgba(255, 255, 255, 0.06);", "--island-hi: rgba(255, 255, 255, 0.03);")
s = s.replace("--island-shadow: 0 24px 60px rgba(0, 0, 0, 0.55), 0 2px 0 rgba(255, 255, 255, 0.04) inset;", "--island-shadow: 0 18px 44px rgba(0, 0, 0, 0.5), 0 2px 0 rgba(255, 255, 255, 0.04) inset;")
p.write_text(s, encoding="utf-8")
print("graphite tokens applied")
