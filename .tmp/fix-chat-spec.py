import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\e2e\chat-features.spec.ts")
s = p.read_text(encoding="utf-8")
s = s.replace("""  await expect(page.getByRole('button', { name: 'Стоп' })).toBeVisible();
  await expect(page.getByText('Думаю')).toBeVisible();
  await expect(page.getByText('Глубокий анализ')).toBeVisible();""",
"""  await expect(page.getByRole('button', { name: 'Стоп' })).toBeVisible();
  await expect(page.getByText('Думаю')).toBeVisible();
  await expect(
    page.getByLabel('Лента сообщений').getByText('Глубокий анализ'),
  ).toBeVisible();""")
s = s.replace("""  await page.getByLabel('Документы для контекста').click();
  await page.getByTitle('Стратегия Atlas на Q1').click();
  await expect(page.getByText('Стратегия Atlas на Q1')).toBeVisible();""",
"""  await page.getByLabel('Документы для контекста').click();
  await page
    .getByRole('option', { name: 'Стратегия Atlas на Q1' })
    .click();
  await expect(
    page.getByRole('button', { name: 'Убрать «Стратегия Atlas на Q1»' }),
  ).toBeVisible();""")
s = s.replace("""  await expect(page.getByText('Глубокий анализ')).toBeVisible();

  const body = await page.evaluate(""",
"""  await expect(
    page.getByLabel('Лента сообщений').getByText('Глубокий анализ'),
  ).toBeVisible();

  const body = await page.evaluate(""")
p.write_text(s, encoding="utf-8")
print("spec adjusted")
