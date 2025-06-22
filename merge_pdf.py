from PyPDF2 import PdfMerger
import os


class Merger:
    def __init__(self, pdf_paths):
        self.pdf_paths = pdf_paths

    def merge_pdf_files(self, output_file):

        try:
            merger = PdfMerger()

            for pdf_path in self.pdf_paths:

                if os.path.exists(pdf_path):
                    merger.append(pdf_path)
                else:
                    print(f"File not found: {pdf_path}")

            merger.write(output_file)
            merger.close()
            print(f"Merged PDF saved to {output_file}")
        except Exception as e:
            print(f"An error occurred: {e}")


