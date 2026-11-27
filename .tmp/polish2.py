import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\home\ui\Home.tsx")
s = p.read_text(encoding="utf-8")
block = """const Muted = styled.p`
  margin: 0;
  font-size: 12.5px;
  color: var(--muted);
`;

"""
assert block in s
s = s.replace(block, "", 1)
p.write_text(s, encoding="utf-8")
print("Muted removed")
