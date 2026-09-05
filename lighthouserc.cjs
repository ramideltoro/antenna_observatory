const cookie = process.env.LHCI_COOKIE;

module.exports = {
  ci: {
    collect: {
      url: [process.env.LHCI_URL || 'http://127.0.0.1:8787/'],
      numberOfRuns: 2,
      settings: {
        chromeFlags: '--headless --no-sandbox --disable-dev-shm-usage',
        extraHeaders: cookie ? { Cookie: cookie } : undefined,
        onlyCategories: ['performance', 'accessibility', 'best-practices'],
      },
    },
    assert: {
      assertions: {
        'categories:performance': ['error', { minScore: 0.85 }],
        'categories:accessibility': ['error', { minScore: 0.95 }],
        'categories:best-practices': ['error', { minScore: 0.95 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 3000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.1 }],
      },
    },
    upload: { target: 'filesystem', outputDir: '.lighthouseci' },
  },
};
