import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\home\ui\Home.tsx")
s = p.read_text(encoding="utf-8")

s = s.replace(
    "                  <HeadMeta>{signals} сигнала</HeadMeta>",
    "                  <HeadMeta>\n                    {signals} {plural(signals, 'сигнал', 'сигнала', 'сигналов')}\n                  </HeadMeta>",
)

old = """              {maxStreak > 0 ? (
                <Muted>
                  {maxStreak} {plural(maxStreak, 'день', 'дня', 'дней')} подряд
                </Muted>
              ) : null}
            </Body>
          </Panel>
        </Widget>
        <Widget variants={ITEM_VARIANTS}>
          <Panel>
            <Body>
              <KpiLabel>Документы</KpiLabel>"""
new = """            </Body>
          </Panel>
        </Widget>
        <Widget variants={ITEM_VARIANTS}>
          <Panel>
            <Body>
              <KpiLabel>Документы</KpiLabel>"""
assert old in s, "kpi streak block not found"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("polish applied")
