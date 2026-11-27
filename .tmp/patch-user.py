import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\shared\api\index.ts")
s = p.read_text(encoding="utf-8")
old = """export interface User {
  id: string;
  username: string;
}"""
new = """export interface User {
  id: string;
  username: string;
  display_name?: string | null;
  avatar_ref?: string | null;
  timezone?: string | null;
}"""
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("User extended")
