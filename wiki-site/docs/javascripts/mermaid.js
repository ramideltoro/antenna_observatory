const mermaidTheme = {
  theme: 'base',
  themeVariables: {
    primaryColor: '#3b2a16',
    primaryTextColor: '#fff4dd',
    primaryBorderColor: '#d69732',
    lineColor: '#d69732',
    secondaryColor: '#211b13',
    tertiaryColor: '#15120e',
    background: '#15120e',
    mainBkg: '#211b13',
    nodeBorder: '#8d6629',
    clusterBkg: '#1b1711',
    clusterBorder: '#60471f',
    edgeLabelBackground: '#211b13',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
};

mermaid.initialize({
  ...mermaidTheme,
  startOnLoad: false,
  securityLevel: 'strict',
});
document$.subscribe(async () => {
  const diagrams = document.querySelectorAll('pre.mermaid');
  if (!diagrams.length) return;
  const nodes = Array.from(diagrams, (diagram) => {
    const node = document.createElement('div');
    node.className = 'mermaid';
    node.textContent = diagram.textContent;
    diagram.replaceWith(node);
    return node;
  });
  try {
    await mermaid.run({ nodes });
  } catch (error) {
    console.error(
      'A documentation diagram could not be rendered.',
      error?.str || error?.message || String(error),
    );
  }
});
