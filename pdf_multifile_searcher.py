#!/usr/bin/env python3

import argparse
from __hello__ import initialized
from dataclasses import dataclass
import pymupdf as fitz
from pprint import pprint  # for easily printing results
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import os
import configparser

#from PIL.ImageOps import expand
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.pdf_multifile_searcher_config.ini')

try:
    # When used as a package
    from .pdf_models import Match
    from .pdf_search import search_pdfs
except Exception:
    # When executed as a script (no package context)
    from pdf_models import Match
    from pdf_search import search_pdfs


class PDFMultifileSearch:
    
    def __init__(self, tk_root, directories, search_pattern):
        self.working_directory = os.getcwd()
        self.tk_root = tk_root
        self.tk_root.title("PDF Multifile Search")
        window_width, window_height = 1200, 800
        window_x_position, window_y_position = 200, 100
        initial_sash_position = 400
        self.tk_root.geometry(f"{window_width}x{window_height}+{window_x_position}+{window_y_position}")

        self.search_directories = directories
        # dictionary with one entry per PDF file
        # each entry is a dictionary, whose key is the page number of the match and the
        # value is a list of rectangles of the match locations
        self.search_results = dict()

        menu_bar = tk.Menu(self.tk_root)

        # Create a "File" menu
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open", command=self.open_pdf)
        file_menu.add_command(label="Add search folder", command=self.add_search_folder)
        file_menu.add_command(label="Clear search folders", command=self.clear_search_folders)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=exit_app)

        # Add the "File" menu to the menu bar
        menu_bar.add_cascade(label="File", menu=file_menu)

        # Configure the window to use the menu bar
        self.tk_root.config(menu=menu_bar)

        # Create the paned window
        self.paned_window = tk.PanedWindow(self.tk_root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self.paned_window.pack(expand=True, fill=tk.BOTH)
        self.search_pane = tk.Frame(self.paned_window, background="lightblue", width=initial_sash_position)
        self.search_pane.rowconfigure(0, weight=1)
        self.search_pane.columnconfigure(0, weight=1)
        self.viewer_pane = tk.Frame(self.paned_window, background="lightgreen")
        self.paned_window.add(self.search_pane, stretch="always")
        self.paned_window.add(self.viewer_pane, stretch="always")
        self.paned_window.paneconfig(self.search_pane, minsize=100)
        self.paned_window.paneconfig(self.viewer_pane, minsize=100)
        # Bind the motion of the sash to the function
        self.paned_window.bind("<B1-Motion>", self.on_sash_drag)

        treeview_style = ttk.Style()
        treeview_style.theme_use("clam")
        treeview_style.configure("Treeview.Heading", background="lightgrey", foreground="black", font=("TkDefaultFont", 10, "normal"))

        # Fill content to the search pane
        # Create a frame to contain the folder tree and its vertical scrollbar.
        self.folder_frame = tk.Frame(self.search_pane)
        self.folder_tree = ttk.Treeview(self.folder_frame)
        # Bind DEL key to remove top-level folder nodes
        self.folder_tree.bind('<Delete>', self._on_folder_tree_delete)
        # Create simple icons for folder and PDF file nodes. Keep references
        # on the instance to avoid garbage collection.
        try:
            self._folder_icon = tk.PhotoImage(width=16, height=16)
            self._folder_icon.put("#F0C419", to=(0, 0, 15, 15))
            self._pdf_icon = tk.PhotoImage(width=16, height=16)
            self._pdf_icon.put("#D9534F", to=(0, 0, 15, 15))
        except Exception:
            # PhotoImage may fail in some headless environments; fall back to None
            self._folder_icon = None
            self._pdf_icon = None
        # Determine initial entries for the folder tree. If search_directories
        # were provided on the command line, show them. Otherwise show the
        # current working directory as a single entry.
        initial_dirs = []
        if self.search_directories:
            initial_dirs = list(self.search_directories)
        else:
            # fallback to current working directory
            initial_dirs = [self.working_directory]

        # Set a reasonable visible-height (rows) up to 10 lines; the scrollbar
        # will allow access to the remainder when there are many entries.
        # Use a fixed visible height (10 rows) so the tree shows multiple
        # lines when expanded; scrolling will handle overflow.
        try:
            self.folder_tree["height"] = 10
        except Exception:
            self.folder_tree["height"] = 6

        self.folder_tree.tag_configure("heading", foreground="red")
        self.folder_tree.column("#0", width=initial_sash_position)
        self.folder_tree.heading("#0", text="Search folders", anchor="w")
        for search_directory in initial_dirs:
            # only insert non-empty strings
            if search_directory:
                # Insert top-level folder node and populate it hierarchically
                top_node = self.folder_tree.insert("", "end", text=search_directory, open=False, image=self._folder_icon, values=(search_directory,))
                try:
                    self._populate_folder_tree(top_node, search_directory)
                except Exception:
                    # If population fails, leave the node empty
                    pass

        # Add a vertical scrollbar for the folder tree and pack both into folder_frame
        self.folder_scrollbar = tk.Scrollbar(self.folder_frame, orient=tk.VERTICAL, command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=self.folder_scrollbar.set)
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.folder_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Pack the containing frame into the search pane
        self.folder_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False)
        # Bind selection on the folder tree so clicking a PDF node loads it into the viewer
        self.folder_tree.bind("<<TreeviewSelect>>", self.on_folder_tree_select)

        self.pattern_frame = tk.Frame(self.search_pane, background="lightblue", width=initial_sash_position)
        self.pattern_frame.pack(side=tk.TOP, fill=tk.X, expand=False)
        pattern_label = tk.Label(self.pattern_frame, text="Search pattern:")
        pattern_label.pack(side=tk.LEFT, fill=None, expand=False)
        self.pattern_entry = tk.Entry(self.pattern_frame)
        if search_pattern is not None:
            self.pattern_entry.insert(0, search_pattern)
        self.pattern_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bind Enter (Return) and keypad Enter to start the search when the entry has focus.
        # Use a dedicated handler so we can explicitly return "break" to stop propagation.
        self.pattern_entry.bind("<Return>", self._on_pattern_entry_return)
        self.pattern_entry.bind("<KP_Enter>", self._on_pattern_entry_return)

        search_button = tk.Button(self.search_pane, text="Search", command=self.search_pdfs)
        search_button.pack(side=tk.TOP, fill=tk.X, expand=False)

        # Search results
        self.search_result_tree = ttk.Treeview(self.search_pane, columns=("context", "page_number", "match_id"))
        self.search_result_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.search_result_tree.heading("#0", text="File")
        self.search_result_tree.heading("context", text="Context")
        self.search_result_tree.heading("page_number", text="Page")
        self.search_result_tree.heading("match_id", text="ID")
        self.search_result_tree.bind("<<TreeviewSelect>>", self.on_treeview_select)
        # Set the result tree's columns' widths
        column_weights = [20, 20]
        column_weights_sum = sum(column_weights)
        self.search_result_tree.column("#0",
                                       width=int(initial_sash_position * (column_weights[0] / column_weights_sum)))
        self.search_result_tree.column("context",
                                       width=int(initial_sash_position * (column_weights[1] / column_weights_sum)))
        self.search_result_tree.column("page_number", width=40, stretch=False)
        self.search_result_tree.column("match_id", width=40, stretch=False)
        # Store full paths mapping for search results (display_text -> full_path)
        self.search_result_paths = {}
        # Track last column width to detect changes
        self._last_file_column_width = self.search_result_tree.column("#0", "width")
        # Bind column resize event
        self.search_result_tree.bind("<ButtonRelease-1>", self._on_column_resize)
        # Schedule periodic check for column width changes
        self._schedule_column_width_check()
        # Fill content to the viewer pane
        self.canvas = tk.Canvas(self.viewer_pane, bg="grey")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Scrollbar
        self.scrollbar = tk.Scrollbar(tk_root, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.tk_root.bind("<Configure>", self.on_resize)
        self.tk_root.update()

        self.paned_window.sash_place(index=0, x=initial_sash_position, y=0)
        self.load_configuration()

    def save_configuration(self):
        """Save the current configuration to a file."""
        config = configparser.ConfigParser()

        # Save the folders in the folder_tree
        folders = []
        for item in self.folder_tree.get_children():
            values = self.folder_tree.item(item, 'values')
            if values and len(values) > 0:
                folders.append(values[0])

        config['Folders'] = {'folders': ','.join(folders)}

        # Save the search pattern
        config['Search'] = {'pattern': self.pattern_entry.get()}

        # Save the window dimensions and position
        config['Window'] = {
            'width': str(self.tk_root.winfo_width()),
            'height': str(self.tk_root.winfo_height()),
            'x': str(self.tk_root.winfo_x()),
            'y': str(self.tk_root.winfo_y())
            }

        # Save the treeview column widths
        config['Treeview'] = {
            'file_column_width': str(self.search_result_tree.column("#0", "width")),
            'context_column_width': str(self.search_result_tree.column("context", "width"))
        }

        # Save the initial sash position
        sash_position = self.paned_window.sash_coord(0)
        if sash_position:
            config['Sash'] = {'position': str(sash_position[0])}

        # Write the configuration to the file
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def load_configuration(self):
        """Load the configuration from a file."""
        config = configparser.ConfigParser()

        # Check if the configuration file exists
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)

            # Load the folders in the folder_tree
            if 'Folders' in config and 'folders' in config['Folders']:
                folders = config['Folders']['folders'].split(',')
                for folder in folders:
                    if folder:
                        top_node = self.folder_tree.insert("", "end", text=folder, open=False, image=self._folder_icon, values=(folder,))
                        try:
                            self._populate_folder_tree(top_node, folder)
                        except Exception:
                            pass

        # Load the search pattern
        if 'Search' in config and 'pattern' in config['Search']:
            self.pattern_entry.delete(0, tk.END)
            self.pattern_entry.insert(0, config['Search']['pattern'])

        # Load the window dimensions and position
        if 'Window' in config:
            window_width = config['Window'].get('width', '1200')
            window_height = config['Window'].get('height', '800')
            window_x = config['Window'].get('x', '200')
            window_y = config['Window'].get('y', '100')
            self.tk_root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")

        # Load the treeview column widths
        if 'Treeview' in config:
            file_column_width = config['Treeview'].get('file_column_width', '200')
            context_column_width = config['Treeview'].get('context_column_width', '200')
            self.search_result_tree.column("#0", width=int(file_column_width))
            self.search_result_tree.column("context", width=int(context_column_width))

        # Load the initial sash position
        if 'Sash' in config and 'position' in config['Sash']:
            initial_sash_position = int(config['Sash']['position'])
            self.paned_window.sash_place(index=0, x=initial_sash_position, y=0)

    def _schedule_column_width_check(self):
        """Schedule periodic check for column width changes."""
        self._check_column_width_change()
        # Schedule next check in 100ms
        self.tk_root.after(100, self._schedule_column_width_check)

    def _check_column_width_change(self):
        """Check if the file column width has changed and update display if needed."""
        try:
            current_width = self.search_result_tree.column("#0", "width")
            if current_width != self._last_file_column_width:
                self._last_file_column_width = current_width
                self._update_file_path_displays()
        except Exception:
            # Ignore errors (e.g., if widget is destroyed)
            pass

    def _on_column_resize(self, event):
        """Handle column resize event."""
        # Schedule update after a short delay to allow resize to complete
        self.tk_root.after(50, self._check_column_width_change)

    def _on_folder_tree_delete(self, event):
        selected = self.folder_tree.selection()
        for node in selected:
            parent = self.folder_tree.parent(node)
            # Only remove top-level nodes (parent is root)
            if not parent:
                self.folder_tree.delete(node)
    def _update_file_path_displays(self):
        """Update all file path displays in the search result tree based on current column width."""
        if not self.search_results:
            return
        
        file_column_width = self.search_result_tree.column("#0", "width")
        
        # Iterate through all top-level items (file paths)
        for item in self.search_result_tree.get_children():
            item_values = self.search_result_tree.item(item, "values")
            if item_values and len(item_values) > 0:
                full_path = item_values[0]
                # Update the displayed text with newly shortened path
                display_path = self.shorten_path_for_width(full_path, file_column_width)
                self.search_result_tree.item(item, text=display_path)

    def shorten_path_for_width(self, file_path, column_width):
        """Shorten a file path to fit within the given column width.
        
        The path is shortened in the middle with '...' to show both the 
        beginning and end of the path.
        """
        # Estimate character width (rough approximation: column_width / 7 pixels per char)
        # This is a rough estimate and may need adjustment based on font
        max_chars = max(10, column_width // 7)
        
        if len(file_path) <= max_chars:
            return file_path
        
        # Calculate how many characters to keep from start and end
        # Reserve 3 characters for '...'
        chars_for_ends = max_chars - 3
        start_chars = chars_for_ends // 2
        end_chars = chars_for_ends - start_chars
        
        return f"{file_path[:start_chars]}...{file_path[-end_chars:]}"

    def on_treeview_select(self, event):
        selected_item = self.search_result_tree.selection()
        if selected_item:
            page_number = None
            match_id = None
            parent_item = self.search_result_tree.parent(selected_item)
            if parent_item:
                # Get the full file path from the parent item's values
                parent_item_values = self.search_result_tree.item(parent_item, "values")
                if parent_item_values and len(parent_item_values) > 0:
                    file_path = parent_item_values[0]  # Full path stored in values
                else:
                    # Fallback to text if values not found
                    file_path = self.search_result_tree.item(parent_item, "text")
                item_values = self.search_result_tree.item(selected_item, "values")
                page_number = int(item_values[1])
                match_id = int(item_values[2])
                #print(f"Subitem clicked: file_path = {file_path}, item_values = {item_values}, parent_item_values = {parent_item_values}")
            else:
                # Get the full file path from the item's values
                item_values = self.search_result_tree.item(selected_item, "values")
                if item_values and len(item_values) > 0:
                    file_path = item_values[0]  # Full path stored in values
                else:
                    # Fallback to text if values not found
                    file_path = self.search_result_tree.item(selected_item, "text")
                #print(f"Mainitem clicked: file_path = {file_path}, item_values = {item_values}")

            self.load_pdf(file_path)
            if page_number:
                self.current_page = page_number
            else:
                self.current_page = 0
            page = self.loaded_pdf_document.load_page(self.current_page)
            self.show_page(page)
            self.tk_root.title(f"PDF Viewer - Page {self.current_page + 1}/{self.loaded_pdf_document.page_count}")

            highlight_rectangles = []
            # Prepare overlay rectangles to draw on the Tk canvas so they match
            # the rendered pixmap scaling exactly. Each entry is a tuple
            # (x0, y0, x1, y1, color, width).
            self._overlay_rects = []
            for match in self.search_results[file_path]:
                if match.page_number == self.current_page:
                    highlight_rectangles.append(match.location)
                    # add a highlight annotation to the PDF document (keeps data persistent)
                    annotation = page.add_highlight_annot(match.location)
                    if match.match_id == match_id:
                        annotation.set_colors(stroke=fitz.pdfcolor["green"])
                        color = "green"
                        line_width = 2
                    else:
                        annotation.set_colors(stroke=fitz.pdfcolor["yellow"])
                        color = "yellow"
                        line_width = 1
                    annotation.update()
                    rect = match.context_location
                    self._overlay_rects.append((rect.x0, rect.y0, rect.x1, rect.y1, color, line_width))
            self.show_page(page)

    def set_sash_position_percentage(self, ratio):
        @dataclass
        class Position:
            x: int
            y: int
        sash_position = Position(x=0, y=0)
        if self.paned_window.cget("orient") == "horizontal":
            sash_position.x = int(ratio * self.tk_root.winfo_width())
        else:
            sash_position.y = int(ratio * self.tk_root.winfo_height())
        self.paned_window.sash_place(index=0, x=sash_position.x, y=sash_position.y)

    def on_sash_drag(self, event):
        current_sash_position = self.paned_window.sash_coord(0)
        if current_sash_position is not None:
            delta = event.x - current_sash_position[0]
            new_sash_position = current_sash_position[0] + delta
            self.paned_window.sash_place(0, new_sash_position, 0)
        if hasattr(self, 'loaded_pdf_document'):
            self.show_page(self.loaded_pdf_document.load_page(self.current_page))
        # Check if column width changed after sash drag
        self.tk_root.after(100, self._check_column_width_change)

    def add_search_folder(self):
        self.working_directory = filedialog.askdirectory()
        # Add the selected directory as a new top-level node with folder icon
        if self.working_directory:
            top_node = self.folder_tree.insert("", "end", text=self.working_directory, open=False, image=self._folder_icon, values=(self.working_directory,))
            try:
                self._populate_folder_tree(top_node, self.working_directory)
            except Exception:
                pass
            # keep a fixed visible height; scrollbar will be used if needed
        self.show_working_directory()

    def clear_search_folders(self):
        # Refresh the folder tree to show the newly selected working directory
        # Clear existing items
        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)
        self.show_working_directory()

    def show_working_directory(self):
        # Keep a small label showing the current working directory under the
        # folder tree. Remove any previous labels with the same name first.
        if hasattr(self, '_working_dir_label') and self._working_dir_label.winfo_exists():
            self._working_dir_label.destroy()
        if self.working_directory:
            self._working_dir_label = tk.Label(self.search_pane, text="Folder: " + self.working_directory)
            self._working_dir_label.pack(pady=4)

    def _on_pattern_entry_return(self, event):
        # Called when the user presses Enter in the pattern entry.
        # Trigger the search and return "break" to stop default handling.
        try:
            self.search_pdfs()
        except Exception as e:
            print(f"Error during search: {e}")
        return "break"

    def _populate_folder_tree(self, parent_node, directory_path, max_depth=3, current_depth=0):
        """Recursively populate the folder_tree under parent_node with folders and pdf files.

        - Folders are inserted as nodes (collapsed by default).
        - PDF files are inserted as child leaf nodes.
        - The recursion depth is limited by max_depth to avoid huge trees.
        """
        if current_depth >= max_depth:
            return
        try:
            entries = sorted(os.listdir(directory_path))
        except Exception:
            return

        for entry in entries:
            full_path = os.path.join(directory_path, entry)
            # skip hidden files and folders
            if entry.startswith('.'):
                continue
            if os.path.isdir(full_path):
                node = self.folder_tree.insert(parent_node, "end", text=entry, open=False, image=self._folder_icon, values=(full_path,))
                # populate one level deeper
                self._populate_folder_tree(node, full_path, max_depth=max_depth, current_depth=current_depth + 1)
            elif os.path.isfile(full_path) and entry.lower().endswith('.pdf'):
                # Use the file name as text but store full path in the node's 'values' for later use
                self.folder_tree.insert(parent_node, "end", text=entry, values=(full_path,), image=self._pdf_icon)

    def on_folder_tree_select(self, event):
        # Called when the user selects an item in the folder tree.
        selected = self.folder_tree.selection()
        if not selected:
            return
        node = selected[0]
        values = self.folder_tree.item(node, 'values')
        if values and len(values) > 0:
            path = values[0]
            if os.path.isfile(path) and path.lower().endswith('.pdf'):
                try:
                    self.load_pdf(path)
                    page = self.loaded_pdf_document.load_page(self.current_page)
                    self.show_page(page)
                    self.tk_root.title(f"PDF Viewer - Page {self.current_page + 1}/{self.loaded_pdf_document.page_count}")
                except Exception as e:
                    print(f"Failed to open PDF '{path}': {e}")
    def open_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if file_path:
            self.load_pdf(file_path)
            self.show_page(self.loaded_pdf_document.load_page(self.current_page))

    def on_resize(self, event):
        if hasattr(self, 'loaded_pdf_document'):
            self.show_page(self.loaded_pdf_document.load_page(self.current_page))

    def search_pdfs(self):
        # Delegate the heavy-lifting search to the standalone function so the
        # GUI class remains focused on presentation. Keep the same public
        # behaviour: populate `self.search_results` and the result tree.
        self.search_result_tree.delete(*self.search_result_tree.get_children())
        self.search_results.clear()
        self.search_result_paths.clear()

        search_pattern = self.pattern_entry.get()
        # Only run search if working_directory is a valid string
        if not isinstance(self.working_directory, str) or not self.working_directory:
            #print("No search folder selected. Please add a folder before searching.")
            return
        try:
            found = search_pdfs(self.working_directory, search_pattern)
        except Exception as e:
            print(f"Error during search: {e}")
            found = {}

        # Copy results into the instance's search_results and populate tree
        self.search_results = found

        # Get the current column width for the File column
        file_column_width = self.search_result_tree.column("#0", "width")
        
        for file_path, matches in self.search_results.items():
            # Shorten the path for display based on column width
            display_path = self.shorten_path_for_width(file_path, file_column_width)
            # Store full path in values tuple, display shortened path as text
            main_item = self.search_result_tree.insert("", "end", text=display_path, values=(file_path,))
            for match in matches:
                self.search_result_tree.insert(main_item, "end", text="", values=(match.context
                                                                                  , match.page_number
                                                                                  , match.match_id
                                                                                  ))

    def load_pdf(self, file_path):
        self.loaded_pdf_document = fitz.open(file_path)
        self.current_page = 0

    def show_page(self, page):
        canvas_width, canvas_height = self.viewer_pane.winfo_width(), self.viewer_pane.winfo_height()

        if hasattr(self, 'loaded_pdf_document'):
            pdf_width, pdf_height = page.rect.width, page.rect.height

            # Calculate the scaling factors for width and height
            scale_x = canvas_width / pdf_width
            scale_y = canvas_height / pdf_height

            # Choose the smaller scaling factor to maintain the aspect ratio
            scale_factor = min(scale_x, scale_y)

            # Calculate the new dimensions of the PDF after scaling
            new_width = pdf_width * scale_factor
            new_height = pdf_height * scale_factor

            pixel_map = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
            # Use the pixmap's actual pixel size to create the Tk image so we don't
            # stretch the image. This keeps overlay coordinates aligned.
            pixel_image = tk.PhotoImage(data=pixel_map.tobytes(), width=pixel_map.width, height=pixel_map.height)

            self.canvas.config(scrollregion=(0, 0, pixel_map.width, pixel_map.height))
            self.canvas.create_image(0, 0, anchor=tk.NW, image=pixel_image)

            # Cleanup previous image reference
            self.canvas.img = pixel_image
            # Remove previous overlay rectangles
            if hasattr(self.canvas, 'overlay_ids'):
                for oid in self.canvas.overlay_ids:
                    try:
                        self.canvas.delete(oid)
                    except Exception:
                        pass
            self.canvas.overlay_ids = []

            # Draw overlay rectangles stored in self._overlay_rects (PDF coords)
            if hasattr(self, '_overlay_rects') and self._overlay_rects:
                # compute actual scale in case integer rounding occurred
                actual_scale_x = pixel_map.width / pdf_width
                actual_scale_y = pixel_map.height / pdf_height
                for (x0, y0, x1, y1, color, lw) in self._overlay_rects:
                    # scale PDF coords to canvas pixels
                    cx0 = x0 * actual_scale_x
                    cy0 = y0 * actual_scale_y
                    cx1 = x1 * actual_scale_x
                    cy1 = y1 * actual_scale_y
                    # Draw context rectangles with a dashed/dotted outline to
                    # indicate they are context areas. Dash pattern is small to
                    # keep it visually subtle.
                    try:
                        oid = self.canvas.create_rectangle(cx0, cy0, cx1, cy1, outline=color, width=lw, dash=(2,5))
                    except Exception:
                        # Older Tk versions may not support dash tuples in the
                        # same way; fall back to a solid outline.
                        oid = self.canvas.create_rectangle(cx0, cy0, cx1, cy1, outline=color, width=lw)
                    self.canvas.overlay_ids.append(oid)

    def next_page(self):
        if self.current_page < self.page_count - 1:
            self.current_page += 1
            page = self.loaded_pdf_document.load_page(self.current_page)
            self.show_page(page)
            self.tk_root.title(f"PDF Viewer - Page {self.current_page + 1}/{self.loaded_pdf_document.page_count}")

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            page = self.loaded_pdf_document.load_page(self.current_page)
            self.show_page(page)
            self.tk_root.title(f"PDF Viewer - Page {self.current_page + 1}/{self.loaded_pdf_document.page_count}")

def exit_app():
    pdf_viewer.save_configuration()
    tk_root.destroy()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PDF multifile search - search text in multiple PDF files')
    parser.add_argument('-f', '--folder', action='append', help='The folder to process')
    parser.add_argument('-p', '--pattern', help='The pattern to search for')
    args = parser.parse_args()

    tk_root = tk.Tk()
    pdf_viewer = PDFMultifileSearch(tk_root, args.folder, args.pattern)

    # Bind the window's close event to the exit_app function
    tk_root.protocol("WM_DELETE_WINDOW", exit_app)

    tk_root.mainloop()
