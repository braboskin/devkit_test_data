import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\e2e\chat-features.spec.ts")
s = p.read_text(encoding="utf-8")
s = s.replace("""  await page.getByLabel('Документы для контекста').click();
  await page
    .getByRole('option', { name: 'Стратегия Atlas на Q1' })
    .click();""",
"""  await page.getByLabel('Документы для контекста').click();
  const options = page.locator(
    '.ant-select-dropdown .ant-select-item-option',
  );
  await expect(options.first()).toBeVisible();
  await options.filter({ hasText: 'Стратегия Atlas на Q1' }).click();""")
p.write_text(s, encoding="utf-8")
print("option locator updated")
