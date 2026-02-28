import React from 'react';
import '../App.css';

const Docs = () => {
    // Example script string for display
    const exampleScript = `<script src="http://localhost:5173/widget.js" data-domain="example.com" data-api="http://localhost:8000"></script>`;

    return (
        <div className="docs-container card">
            <h2>Configuration Guide</h2>
            <div className="docs-content">
                <p>1. Add the script tag to your website HTML.</p>
                <p>2. Ensure the domain and API URL are correct.</p>
                <p>3. If you use HTTPS, your API must also be HTTPS.</p>
                <ul>
                    <li>Common issue: CORS misconfiguration on your API.</li>
                    <li>Common issue: Mixed content (HTTPS site calling HTTP API).</li>
                </ul>
                <div className="code-snippet">
                    {exampleScript}
                </div>
            </div>
        </div>
    );
};

export default Docs;
