import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\chat\ui\Chat.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace("""              <IconButton
                type="button"
                label={""", """              <IconButton
                htmlType="button"
                label={""")
s = s.replace("""                <Button
                  type="button"
                  variant="danger"
                  onClick={() => void cancelStream()}
                >""", """                <Button
                  htmlType="button"
                  variant="danger"
                  onClick={() => void cancelStream()}
                >""")
p.write_text(s, encoding="utf-8")
print("fixed button types")
