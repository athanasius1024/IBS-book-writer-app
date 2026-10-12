#!/bin/bash
# LaTeX Setup and Testing Script for Terran Society Book

set -e  # Exit on error

echo "==================================="
echo "LaTeX Setup for Terran Society Book"
echo "==================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "This script requires sudo privileges."
    echo "Please run: sudo bash scripts/setup_latex.sh"
    exit 1
fi

# Update package list
echo "Step 1: Updating package list..."
apt-get update

# Install XeLaTeX and fonts
echo ""
echo "Step 2: Installing XeLaTeX and fonts..."
echo "This may take several minutes and requires ~500MB-1GB of space."
echo ""
apt-get install -y texlive-xetex texlive-fonts-recommended texlive-fonts-extra texlive-latex-extra

# Verify installation
echo ""
echo "Step 3: Verifying installation..."
if command -v xelatex &> /dev/null; then
    echo "✓ XeLaTeX installed successfully"
    xelatex --version | head -1
else
    echo "✗ XeLaTeX installation failed"
    exit 1
fi

if command -v pdflatex &> /dev/null; then
    echo "✓ PDFLaTeX installed successfully"
else
    echo "✗ PDFLaTeX not found (optional)"
fi

# Test PDF generation
echo ""
echo "Step 4: Testing PDF generation from Markdown..."
cd /media/infodine/LaCie/z_stash/z-terran/TerranSocietyBook/infobuild

if [ -f "book/manuscript.md" ]; then
    echo "Converting manuscript.md to PDF using XeLaTeX..."
    pandoc book/manuscript.md -o book/TerranSocietyBook_latex.pdf \
        --pdf-engine=xelatex \
        --toc \
        --toc-depth=3 \
        -V geometry:margin=1in \
        -V fontsize=11pt \
        -V documentclass=book \
        2>&1 | tail -20
    
    if [ -f "book/TerranSocietyBook_latex.pdf" ]; then
        echo "✓ PDF generated successfully!"
        ls -lh book/TerranSocietyBook_latex.pdf
    else
        echo "✗ PDF generation failed"
        exit 1
    fi
else
    echo "⚠ Manuscript file not found. Generate it first with:"
    echo "  python3 scripts/generate_book.py"
fi

echo ""
echo "==================================="
echo "Installation complete!"
echo "==================================="
echo ""
echo "You can now use the 'Convert to PDF > From MD (XeLaTeX)' option"
echo "in the web interface, or run:"
echo ""
echo "  pandoc book/manuscript.md -o book/TerranSocietyBook.pdf \\"
echo "    --pdf-engine=xelatex --toc --toc-depth=3 \\"
echo "    -V geometry:margin=1in \\"
echo "    -V fontsize=11pt \\"
echo "    -V documentclass=book"
echo ""
