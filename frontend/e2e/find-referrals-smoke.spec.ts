import { expect, test } from '@playwright/test';

async function installCommonMocks(page) {
  await page.route('**/api/v1/credits/balance', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: { balance: 0 }, meta: {} }),
    });
  });

  await page.route('**/api/v1/preferences/job', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: { target_role: 'Backend Engineer', target_seniority: 'senior' },
        meta: {},
      }),
    });
  });

  await page.route('**/api/v1/search/recommendations**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: { recommendations: [], scan_stats: { uncached_count: 0 } },
        meta: {},
      }),
    });
  });

  await page.route('**/api/v1/companies/suggest**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [], meta: {} }),
    });
  });

  await page.route('**/api/v1/companies?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [], meta: {} }),
    });
  });

  await page.route('**/api/v1/companies/discover', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: { jobs_found: 0, careers_url: null }, meta: {} }),
    });
  });
}

test('low credits + low coverage keeps own-network and shows limit message', async ({ page }) => {
  await installCommonMocks(page);
  await page.route('**/api/v1/search/smart', async (route) => {
    await route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Daily search limit reached (50/day)' }),
    });
  });

  await page.goto('/qa/find-referrals-smoke');
  await expect(page.getByRole('heading', { name: 'Find Referral Paths' })).toBeVisible();

  const companyInput = page.getByRole('combobox');
  await companyInput.fill('Stripe');
  await companyInput.press('Enter');

  await expect(page.getByText('You need 5 credits to search All Networks.')).toBeVisible();

  await page.getByRole('button', { name: 'Find Referral Paths' }).click();
  await expect(page.getByText("You've reached today's search limit. Please try again tomorrow.")).toBeVisible();
});

test('insufficient credits on search shows Go to Credits CTA', async ({ page }) => {
  await installCommonMocks(page);
  await page.route('**/api/v1/search/smart', async (route) => {
    await route.fulfill({
      status: 402,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Insufficient credits for marketplace search. You need 5 credits.',
      }),
    });
  });

  await page.goto('/qa/find-referrals-smoke');
  await expect(page.getByRole('heading', { name: 'Find Referral Paths' })).toBeVisible();

  const companyInput = page.getByRole('combobox');
  await companyInput.fill('Stripe');
  await companyInput.press('Enter');

  await page.getByRole('radio', { name: /All Networks/i }).click();
  await page.getByRole('button', { name: 'Find Referral Paths' }).click();

  await expect(page.getByText("You don't have enough credits for this action yet.")).toBeVisible();
  await expect(page.getByRole('link', { name: /Go to Credits/i })).toBeVisible();
});
