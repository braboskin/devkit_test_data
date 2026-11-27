import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\playwright.config.ts")
s = p.read_text(encoding="utf-8")
old = "  use: {\n    baseURL: 'http://127.0.0.1:4173',\n    trace: 'on-first-retry',\n  },"
new = "  use: {\n    baseURL: 'http://127.0.0.1:4173',\n    trace: 'on-first-retry',\n    // dist регистрирует service worker, а он перехватывает fetch в обход\n    // page.route — моки /api/** не применялись бы. Для e2e SW отключаем.\n    serviceWorkers: 'block',\n  },"
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("serviceWorkers blocked")
