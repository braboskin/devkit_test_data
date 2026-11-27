import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\home\ui\Home.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace('<Button type="submit" variant="primary" disabled={creating}>', '<Button htmlType="submit" variant="primary" disabled={creating}>')
s = s.replace('''                  <Button
                    type="button"
                    variant="ghost"''', '''                  <Button
                    variant="ghost"''')
p.write_text(s, encoding="utf-8")
print("htmlType fixed")
