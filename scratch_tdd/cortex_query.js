async function query(text, k, workflow) {
    let documentClass;
    switch(workflow) {
        case 'validate-design':
            documentClass = 'DesignDocument';
            break;
        case 'technical-debate':
            documentClass = 'DebateDocument';
            break;
        case 'iterative-implement':
            documentClass = 'ImplementationDocument';
            break;
        default:
            throw new Error('Invalid workflow name');
    }

    const response = await fetch('http://localhost:8080/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, k, document_class: documentClass })
    });
    const data = await response.json();
    return data.paragraphs;
}

if (require.main === module) {
    const args = process.argv.slice(2);
    const workflowIndex = args.indexOf('--workflow');
    
    if (workflowIndex === -1 || workflowIndex === args.length - 1) {
        console.error('Invalid workflow name');
        process.exit(1);
    }
    
    const workflow = args[workflowIndex + 1];
    
    const text = args.find(a => !a.startsWith('--') && a !== workflow) || '';
    const k = 1;
    
    query(text, k, workflow).then(console.log).catch(err => {
        console.error(err.message);
        process.exit(1);
    });
}

module.exports = query;
