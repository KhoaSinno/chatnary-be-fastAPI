#!/usr/bin/env python3
"""
PDF Processing Test Tool
Test OCR and text extraction on specific PDF files

Usage:
  python test_pdf.py <filename>          # Test specific file
  python test_pdf.py                     # List available PDFs
  docker compose exec api python test_pdf.py <filename>
"""

from app.pdf_processor import pdf_processor
import sys
import pathlib
sys.path.insert(0, '/app')


def list_available_pdfs():
    """List all PDF files in data directory"""
    data_dir = pathlib.Path("/data")
    pdfs = list(data_dir.glob("*.pdf"))

    if not pdfs:
        print("❌ No PDF files found in /data")
        return

    print("📚 Available PDF files:")
    for i, pdf in enumerate(pdfs, 1):
        size_kb = pdf.stat().st_size / 1024
        print(f"  {i}. {pdf.name} ({size_kb:.1f} KB)")


def test_pdf_processing(pdf_filename):
    """Test PDF processing with detailed output"""
    pdf_path = pathlib.Path(f"/data/{pdf_filename}")

    if not pdf_path.exists():
        print(f"❌ File not found: {pdf_path}")
        print("\nTip: Use 'python test_pdf.py' to list available files")
        return False

    print(f"🔍 Testing PDF processing for: {pdf_filename}")
    print(f"📄 File size: {pdf_path.stat().st_size / 1024:.1f} KB")

    # Check system capabilities
    caps = pdf_processor.get_capabilities()
    print(f"🛠️ System capabilities:")
    for key, value in caps.items():
        status = "✅" if value else "❌"
        print(f"   {status} {key}: {value}")

    # Test extraction
    print(f"\n⏳ Starting text extraction...")
    try:
        text = pdf_processor.extract_text(pdf_path)

        if text.strip():
            print(f"✅ SUCCESS!")
            print(f"📊 Extracted {len(text)} characters")

            # Count lines and words
            lines = len(text.splitlines())
            words = len(text.split())
            print(f"📈 Statistics: {lines} lines, {words} words")

            print(f"\n📄 Content preview (first 500 chars):")
            print("=" * 60)
            print(text[:500] + ("..." if len(text) > 500 else ""))
            print("=" * 60)

            return True
        else:
            print(f"❌ No text extracted")
            return False

    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        return False


if __name__ == "__main__":
    print("🔧 PDF Processing Test Tool")
    print("=" * 40)

    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        success = test_pdf_processing(pdf_file)
        sys.exit(0 if success else 1)
    else:
        list_available_pdfs()
        print("\nUsage: python test_pdf.py <filename>")
        sys.exit(0)
