import { mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

import * as chromeLauncher from 'chrome-launcher';
import lighthouse from 'lighthouse';

const cookie = process.env.LHCI_COOKIE;
const url = process.env.LHCI_URL || 'http://127.0.0.1:8787/';
const outputDirectory = path.resolve('.lighthouseci');

if (!cookie) {
  throw new Error(
    'LHCI_COOKIE is required so Lighthouse audits the authenticated dashboard.',
  );
}

const thresholds = {
  accessibility: 0.95,
  'best-practices': 0.95,
  performance: 0.85,
};

await rm(outputDirectory, { force: true, recursive: true });
await mkdir(outputDirectory, { recursive: true });

const chrome = await chromeLauncher.launch({
  chromeFlags: ['--headless', '--no-sandbox', '--disable-dev-shm-usage'],
});
const observations = [];

try {
  for (let run = 1; run <= 3; run += 1) {
    const result = await lighthouse(url, {
      extraHeaders: { Cookie: cookie },
      logLevel: 'warn',
      onlyCategories: Object.keys(thresholds),
      output: 'json',
      port: chrome.port,
    });

    if (!result)
      throw new Error(`Lighthouse run ${run} did not return a report.`);
    await writeFile(
      path.join(outputDirectory, `run-${run}.report.json`),
      result.report,
    );

    const scores = Object.fromEntries(
      Object.keys(thresholds).map((category) => [
        category,
        result.lhr.categories[category].score,
      ]),
    );
    const largestContentfulPaint =
      result.lhr.audits['largest-contentful-paint'].numericValue;
    const cumulativeLayoutShift =
      result.lhr.audits['cumulative-layout-shift'].numericValue;

    console.log(
      `Run ${run}: performance=${scores.performance.toFixed(2)} ` +
        `accessibility=${scores.accessibility.toFixed(2)} ` +
        `best-practices=${scores['best-practices'].toFixed(2)} ` +
        `LCP=${Math.round(largestContentfulPaint)}ms CLS=${cumulativeLayoutShift.toFixed(3)}`,
    );
    observations.push({
      cumulativeLayoutShift,
      largestContentfulPaint,
      scores,
    });
  }
} finally {
  chrome.kill();
}

const median = (values) => [...values].sort((left, right) => left - right)[1];
const representative = {
  cumulativeLayoutShift: median(
    observations.map(({ cumulativeLayoutShift }) => cumulativeLayoutShift),
  ),
  largestContentfulPaint: median(
    observations.map(({ largestContentfulPaint }) => largestContentfulPaint),
  ),
  scores: Object.fromEntries(
    Object.keys(thresholds).map((category) => [
      category,
      median(observations.map(({ scores }) => scores[category])),
    ]),
  ),
};
const failures = [];

console.log(
  `Median: performance=${representative.scores.performance.toFixed(2)} ` +
    `accessibility=${representative.scores.accessibility.toFixed(2)} ` +
    `best-practices=${representative.scores['best-practices'].toFixed(2)} ` +
    `LCP=${Math.round(representative.largestContentfulPaint)}ms ` +
    `CLS=${representative.cumulativeLayoutShift.toFixed(3)}`,
);

for (const [category, minimum] of Object.entries(thresholds)) {
  if (representative.scores[category] < minimum) {
    failures.push(
      `${category} ${representative.scores[category].toFixed(2)} is below ${minimum.toFixed(2)}`,
    );
  }
}
if (representative.largestContentfulPaint > 3000) {
  failures.push(
    `largest-contentful-paint ${Math.round(representative.largestContentfulPaint)}ms exceeds 3000ms`,
  );
}
if (representative.cumulativeLayoutShift > 0.1) {
  failures.push(
    `cumulative-layout-shift ${representative.cumulativeLayoutShift.toFixed(3)} exceeds 0.100`,
  );
}

if (failures.length) {
  throw new Error(`Lighthouse budgets failed:\n- ${failures.join('\n- ')}`);
}
