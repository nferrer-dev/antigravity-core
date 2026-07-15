fetch('http://127.0.0.1:4747/snapshot')
  .then(r => r.json())
  .then(s => {
    console.log('Length:', s.html.length);
    console.log('Article tags:', !!s.html.match(/<[^>]*role=["']?article["']?[^>]*>/i));
    console.log('Message classes:', !!s.html.match(/class=["'][^"]*message[^"]*["']/i));
    console.log('Wrapper classes:', !!s.html.match(/class=["'][^"]*(leading-relaxed select-text|whitespace-pre-wrap)[^"]*["']/i));
    console.log('Wrapper class detailed:', !!s.html.match(/(leading-relaxed select-text|whitespace-pre-wrap)/i));
  })
  .catch(console.error);
