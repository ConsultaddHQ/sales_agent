#!/bin/bash
#
# Deploy Demo to GitHub Pages
# This deploys ONLY the static demo page (not backend services)
#

set -e

echo "======================================"
echo "  GitHub Pages Deployment"
echo "======================================"
echo ""

# Check if git repo exists
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
    git branch -M main
fi

# Check if demo_pages directory exists
if [ ! -d "demo_pages" ]; then
    echo "❌ Error: demo_pages directory not found!"
    echo "Please run workflow.py first to generate demo pages"
    exit 1
fi

# Create gh-pages branch if it doesn't exist
if ! git show-ref --verify --quiet refs/heads/gh-pages; then
    echo "Creating gh-pages branch..."
    git checkout --orphan gh-pages
    git rm -rf . 2>/dev/null || true
else
    echo "Switching to gh-pages branch..."
    git checkout gh-pages
fi

# Copy demo pages
echo "Copying demo pages..."
cp -r demo_pages/* .

# Create index.html if it doesn't exist
if [ ! -f "index.html" ]; then
    echo "Creating index.html..."
    cat > index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Shopping Assistant Demo</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        h1 { margin-bottom: 30px; }
        .demo-list {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        .demo-item {
            padding: 15px;
            margin: 10px 0;
            background: rgba(255,255,255,0.1);
            border-radius: 5px;
            transition: all 0.3s;
        }
        .demo-item:hover {
            background: rgba(255,255,255,0.2);
            transform: translateX(5px);
        }
        a {
            color: white;
            text-decoration: none;
            font-size: 18px;
        }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>🤖 AI Shopping Assistant Demo</h1>
    <div class="demo-list">
        <p>Select a demo to try the AI shopping assistant:</p>
EOF

    # Add links to all demo files
    for file in demo_*.html; do
        if [ -f "$file" ]; then
            echo "        <div class='demo-item'><a href='$file'>$file</a></div>" >> index.html
        fi
    done

    cat >> index.html << 'EOF'
    </div>
</body>
</html>
EOF
fi

# Commit and push
echo "Committing changes..."
git add .
git commit -m "Deploy demo pages" || echo "No changes to commit"

echo ""
echo "======================================"
echo "  Ready to deploy!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Create a GitHub repository (if you haven't)"
echo "2. Add remote:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
echo ""
echo "3. Push gh-pages branch:"
echo "   git push -u origin gh-pages"
echo ""
echo "4. Enable GitHub Pages:"
echo "   - Go to repository Settings > Pages"
echo "   - Source: Deploy from a branch"
echo "   - Branch: gh-pages"
echo "   - Folder: / (root)"
echo ""
echo "5. Your demo will be available at:"
echo "   https://YOUR_USERNAME.github.io/YOUR_REPO/"
echo ""
echo "⚠️  IMPORTANT: Backend services (image server, search API)"
echo "    cannot run on GitHub Pages. You need to:"
echo "    - Host them on Railway/Render/Vercel"
echo "    - Update URLs in the demo page"
echo ""

# Switch back to main branch
git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
