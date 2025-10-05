"""Search utilities for the PDF multifile searcher.

Provides a standalone function `search_pdfs` that searches a directory tree for
PDF files and returns a mapping of file paths to lists of `Match` objects.
This logic was extracted from the GUI class to make it testable and reusable.
"""
import os
from typing import Dict, List
import pymupdf as fitz
try:
    # When used as a package
    from .pdf_models import Match
except Exception:
    # When executed as a standalone module
    from pdf_models import Match


def search_pdfs(working_directory: str, search_pattern: str) -> Dict[str, List[Match]]:
    """Search all PDF files under `working_directory` for `search_pattern`.

    Returns a dict mapping absolute file paths to lists of Match objects.
    """
    import concurrent.futures
    results: Dict[str, List[Match]] = {}
    match_id_counter = [0]  # mutable counter for unique match IDs

    # Gather all PDF file paths first
    pdf_files = []
    for root, dirs, files in os.walk(working_directory):
        for filename in files:
            if filename.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, filename))

    def process_pdf(pdf_file_path):
        local_results = []
        try:
            pdf_document = fitz.open(pdf_file_path)
        except Exception:
            return pdf_file_path, local_results
        for page_number in range(pdf_document.page_count):
            page = pdf_document[page_number]
            try:
                search_results_on_current_page = page.search_for(search_pattern)
            except Exception:
                search_results_on_current_page = []
            if not search_results_on_current_page:
                continue
            for mr in search_results_on_current_page:
                match_height = mr.y1 - mr.y0
                page_h = page.rect.height
                pad_y = max(5, match_height * 0.5)
                y0 = max(0, mr.y0 - pad_y)
                y1 = min(page_h, mr.y1 + pad_y)
                context_location = fitz.Rect(mr.x0 - 50, y0, mr.x1 + 50, y1)
                try:
                    context_text = page.get_textbox(context_location)
                except Exception:
                    context_text = ""
                # Thread-safe match_id assignment
                match_id = None
                # Use a lock to increment the counter safely
                if hasattr(process_pdf, 'lock'):
                    with process_pdf.lock:
                        match_id = match_id_counter[0]
                        match_id_counter[0] += 1
                else:
                    match_id = match_id_counter[0]
                    match_id_counter[0] += 1
                local_results.append(Match(match_id, page_number, mr, context_location, context_text))
        pdf_document.close()
        return pdf_file_path, local_results

    # Add a lock for thread-safe match_id increment
    import threading
    process_pdf.lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_pdf = {executor.submit(process_pdf, pdf_file): pdf_file for pdf_file in pdf_files}
        for future in concurrent.futures.as_completed(future_to_pdf):
            pdf_file_path, matches = future.result()
            if matches:
                results[pdf_file_path] = matches

    return results
