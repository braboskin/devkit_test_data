import pathlib

p = pathlib.Path(__file__).with_name("mockup.html")
s = p.read_text(encoding="utf-8")


def replace_region(text, start_marker, end_marker, new_block):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + new_block + text[end:]


PALETTE = """  /* ─── Graphite: обе темы, акцент ставится из настроек ───────── */
  body {
    --accent: #1d4ed8;
    --accent-soft: rgba(29, 78, 216, .16);
    --on-accent: #ffffff;
    --glow1: rgba(29, 78, 216, .26);
    --glow2: rgba(148, 163, 184, .14);
    --bg0: #07080a;
    --bg1: #171a20;
    --surface: rgba(24, 27, 33, .52);
    --raised: rgba(30, 34, 41, .80);
    --sunken: rgba(9, 10, 12, .88);
    --hover: rgba(255, 255, 255, .05);
    --text: #eef1f5;
    --muted: #a4abb6;
    --faint: #7d858f;
    --border: rgba(255, 255, 255, .085);
    --border-strong: rgba(255, 255, 255, .14);
    --ok: #34d399;
    --warn: #fbbf24;
    --shadow: 0 24px 60px -28px rgba(0, 0, 0, .9);
  }

  body[data-mode="light"] {
    --accent: #1d4ed8;
    --accent-soft: rgba(29, 78, 216, .10);
    --on-accent: #ffffff;
    --glow1: rgba(29, 78, 216, .12);
    --glow2: rgba(148, 163, 184, .22);
    --bg0: #f7f8fa;
    --bg1: #e7ebf1;
    --surface: rgba(255, 255, 255, .62);
    --raised: rgba(255, 255, 255, .90);
    --sunken: rgba(255, 255, 255, .95);
    --hover: rgba(15, 23, 42, .05);
    --text: #12161c;
    --muted: #4b5563;
    --faint: #6b7280;
    --border: rgba(15, 23, 42, .10);
    --border-strong: rgba(15, 23, 42, .18);
    --ok: #047857;
    --warn: #b45309;
    --shadow: 0 20px 44px -28px rgba(15, 23, 42, .38);
  }

"""
s = replace_region(s, "  /* ─── палитра A: Atlas Navy", "  /* ─── база", PALETTE)

SETTINGS_CSS = """  /* ─── настройки ─────────────────────────────────────────────── */
  .settings-grid { grid-template-columns: 1.5fr 1fr; }
  .stack-sm { display: flex; flex-direction: column; gap: 12px; }
  .field { display: flex; flex-direction: column; gap: 6px; }
  .field > label {
    font-size: 11.5px; font-weight: 500; letter-spacing: .08em;
    text-transform: uppercase; color: var(--faint);
  }
  .input {
    display: flex; align-items: center; gap: 8px;
    height: 36px; padding: 0 11px; border-radius: 10px;
    background: var(--sunken); border: 1px solid var(--border);
    font-size: 13.5px;
  }
  .input.focus {
    border-color: color-mix(in srgb, var(--accent) 65%, transparent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }
  .input .link { margin-left: auto; font-size: 12px; color: var(--accent); }
  .input .chev { margin-left: auto; color: var(--faint); }
  .rel { position: relative; }
  .hint-line { font-size: 11.5px; color: var(--faint); }
  .menu {
    position: absolute; z-index: 20; top: 100%; left: 0; margin-top: 6px; min-width: 260px;
    border-radius: 12px; padding: 6px;
    background: var(--raised);
    backdrop-filter: blur(var(--blur-raised)) saturate(160%);
    border: 1px solid var(--border-strong);
    box-shadow: var(--shadow);
  }
  .menu-item {
    display: flex; align-items: center; gap: 8px;
    height: 32px; padding: 0 9px; border-radius: 8px; font-size: 13px;
  }
  .menu-item:hover { background: var(--hover); }
  .menu-item.active { background: var(--accent-soft); color: var(--text); }
  .menu-item .mono { margin-left: auto; color: var(--faint); }
  .menu-sep { height: 1px; background: var(--border); margin: 5px 4px; }
  .menu-note { padding: 4px 9px 6px; font-size: 11.5px; color: var(--faint); }
  .seg {
    display: inline-flex; gap: 2px; padding: 3px; border-radius: 11px;
    background: var(--sunken); border: 1px solid var(--border);
  }
  .seg button { height: 28px; padding: 0 12px; border-radius: 8px; font-size: 12.5px; color: var(--muted); }
  .seg button[aria-pressed="true"] { background: var(--accent); color: var(--on-accent); }
  .swatches { display: flex; gap: 8px; flex-wrap: wrap; }
  .swatch {
    width: 26px; height: 26px; border-radius: 9px;
    border: 1px solid rgba(255, 255, 255, .18);
  }
  .swatch[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--bg0), 0 0 0 3.5px var(--text); }
  .toggle {
    display: block; width: 38px; height: 22px; border-radius: 999px;
    background: var(--accent); position: relative;
  }
  .toggle::after {
    content: ""; position: absolute; top: 3px; right: 3px;
    width: 16px; height: 16px; border-radius: 50%; background: var(--on-accent);
  }
  .setting-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 0; border-bottom: 1px solid var(--border);
  }
  .setting-row:last-child { border-bottom: 0; }
  .setting-row .t { font-size: 13.5px; }
  .setting-row .s { font-size: 11.5px; color: var(--faint); margin-top: 2px; }
  .setting-row .ctl { margin-left: auto; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip {
    height: 26px; padding: 0 10px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--hover);
    font-size: 12px; color: var(--muted);
  }
  .chip[aria-pressed="true"] {
    background: var(--accent-soft);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
    color: var(--text);
  }

"""
s = s.replace("  /* ─── S3: тост ──────────────────────────────────────────────── */",
              SETTINGS_CSS + "  /* ─── S3: тост ──────────────────────────────────────────────── */", 1)

s = s.replace('  body[data-screen="chat"] #chat { display: flex; }',
              '  body[data-screen="chat"] #chat { display: flex; }\n'
              '  body[data-screen="settings"] #settings { display: block; }', 1)

CHEV = ('<svg class="chev" viewBox="0 0 24 24" width="16" height="16" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>')

ACCENTS = [
    ("#1d4ed8", "синий"),
    ("#0284c7", "небо"),
    ("#059669", "изумруд"),
    ("#7c3aed", "фиолет"),
    ("#db2777", "роза"),
    ("#ea580c", "оранж"),
    ("#b91c1c", "красный"),
    ("#334155", "графит"),
]
swatches = "\n".join(
    f'                      <button class="swatch" data-accent="{color}" title="{name}" '
    f'style="background:{color}" aria-pressed="false"></button>'
    for color, name in ACCENTS
)

SETTINGS = f"""
      <section id="settings" class="screen">
        <div class="page-head">
          <div>
            <div class="eyebrow">Настройки</div>
            <h1>Аккаунт и интерфейс</h1>
            <div class="sub">Модель, оформление и подключённые сервисы.</div>
          </div>
        </div>

        <div class="grid settings-grid">
          <div class="col">
            <section class="panel">
              <div class="panel-head">
                <h2>Модель</h2>
                <span class="pill pill-ok"><span class="dot"></span>ключ работает</span>
                <span class="more">deepseek-chat</span>
              </div>
              <div class="panel-body stack-sm">
                <div class="field">
                  <label>Провайдер</label>
                  <div class="select">
                    <span class="msg-avatar" style="width:20px;height:20px;border-radius:6px;font-size:10px">D</span>
                    DeepSeek
                    {CHEV}
                  </div>
                  <div class="hint-line">Адрес API подставится из каталога: https://api.deepseek.com/v1</div>
                </div>

                <div class="field">
                  <label>API-ключ</label>
                  <div class="input">
                    <span class="mono">sk-••••••••••••••••••••••••7f3a</span>
                    <button class="link">Заменить</button>
                  </div>
                </div>

                <div class="field rel">
                  <label>Модель</label>
                  <div class="input focus">
                    deepseek-chat
                    {CHEV}
                  </div>
                  <div class="menu">
                    <div class="menu-item active">deepseek-chat <span class="mono">быстрая</span></div>
                    <div class="menu-item">deepseek-reasoner <span class="mono">рассуждения</span></div>
                    <div class="menu-sep"></div>
                    <div class="menu-note">2 модели получены с api.deepseek.com · Enter — выбор</div>
                  </div>
                </div>

                <div class="row">
                  <button class="btn">Загрузить модели</button>
                  <button class="btn">Проверить подключение</button>
                  <button class="btn btn-primary" style="margin-left:auto">Сохранить</button>
                </div>
                <div class="hint-line">Ключ хранится на сервере зашифрованным и маскируется в API.</div>
              </div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2>Яндекс.Диск</h2>
                <span class="pill pill-ok"><span class="dot"></span>подключён</span>
                <span class="more">Отключить</span>
              </div>
              <div class="panel-body">
                <div class="doc" style="border-bottom:0">
                  <div class="doc-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M7 12h10"/></svg>
                  </div>
                  <div>
                    <div class="doc-title">Личный диск</div>
                    <div class="doc-sub">Оригиналы больше 20 МБ и бэкапы · 24 ГБ свободно</div>
                  </div>
                  <button class="btn" style="margin-left:auto">Проверить доступ</button>
                </div>
              </div>
            </section>
          </div>

          <div class="col">
            <section class="panel">
              <div class="panel-head">
                <h2>Оформление</h2>
                <span class="more">применяется сразу</span>
              </div>
              <div class="panel-body">
                <div class="setting-row">
                  <div>
                    <div class="t">Тема</div>
                    <div class="s">Системная следует за ОС</div>
                  </div>
                  <div class="ctl seg">
                    <button data-mode="light">Светлая</button>
                    <button data-mode="dark" aria-pressed="true">Тёмная</button>
                    <button data-mode="system">Системная</button>
                  </div>
                </div>

                <div class="setting-row">
                  <div>
                    <div class="t">Акцент</div>
                    <div class="s">Кнопки, ссылки, фокус, прогресс</div>
                  </div>
                  <div class="ctl swatches">
{swatches}
                  </div>
                </div>

                <div class="setting-row">
                  <div>
                    <div class="t">Эффекты и прозрачность</div>
                    <div class="s">Стекло, размытие, анимации</div>
                  </div>
                  <div class="ctl">
                    <span class="toggle" role="switch" aria-checked="true"></span>
                  </div>
                </div>

                <div class="setting-row">
                  <div>
                    <div class="t">Фон</div>
                    <div class="s">Градиент за стеклом</div>
                  </div>
                  <div class="ctl chips">
                    <button class="chip" aria-pressed="true">Нет</button>
                    <button class="chip">Aurora</button>
                    <button class="chip">Mist</button>
                    <button class="chip">Night</button>
                  </div>
                </div>
              </div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2>Уведомления</h2>
                <span class="more">push на этом устройстве</span>
              </div>
              <div class="panel-body">
                <div class="setting-row">
                  <div>
                    <div class="t">Напоминания</div>
                    <div class="s">Задачи и привычки</div>
                  </div>
                  <div class="ctl">
                    <span class="toggle" role="switch" aria-checked="true"></span>
                  </div>
                </div>
                <div class="setting-row">
                  <div>
                    <div class="t">Тихие часы</div>
                    <div class="s">23:00 — 08:00</div>
                  </div>
                  <div class="ctl"><span class="pill">изменить</span></div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </section>
"""

if "    </main>" not in s:
    raise SystemExit("anchor </main> not found")
s = s.replace("    </main>", SETTINGS + "    </main>", 1)

OLD_SCRIPT_START = "  const params = new URLSearchParams(location.search);"
start = s.index(OLD_SCRIPT_START)
end = s.index("</script>", start)
NEW_SCRIPT = """  const params = new URLSearchParams(location.search);
  const mode = params.get('mode') || 'dark';
  const screenName = params.get('screen') || 'home';
  const accent = params.get('accent') || '#1d4ed8';

  document.body.dataset.mode = mode;
  document.body.dataset.screen = screenName;
  document.body.style.setProperty('--accent', accent);
  document.body.style.setProperty(
    '--accent-soft',
    `color-mix(in srgb, ${accent} ${mode === 'light' ? 12 : 16}%, transparent)`,
  );
  document.body.style.setProperty('--on-accent', '#ffffff');
  document.body.style.setProperty(
    '--glow1',
    `color-mix(in srgb, ${accent} ${mode === 'light' ? 14 : 26}%, transparent)`,
  );

  const items = document.querySelectorAll('.nav .nav-item');
  items.forEach((item) => item.removeAttribute('aria-current'));
  const navIndex = { home: 0, chat: 2, settings: 9 }[screenName] ?? 0;
  if (items[navIndex]) items[navIndex].setAttribute('aria-current', 'page');

  document.querySelectorAll('.seg button[data-mode]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  });
  document.querySelectorAll('.swatch').forEach((swatch) => {
    swatch.setAttribute(
      'aria-pressed',
      String(swatch.dataset.accent.toLowerCase() === accent.toLowerCase()),
    );
  });
"""
s = s[:start] + NEW_SCRIPT + s[end:]

p.write_text(s, encoding="utf-8")
print("ok", len(s))
