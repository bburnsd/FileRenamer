import os
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from PIL import Image, ImageTk, ExifTags
import threading  # Import threading module
import queue  # Import queue module
from pyupdater.client import Client
from pyupdater.client.downloader import FileDownloader
import requests  # Import requests for GitHub API
from packaging import version  # Import version for version comparison

#This is v0.1.1 File Renamer by Brad Davis
#Capabilities of this program are straight forward and in the README.md

class FileRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Renamer Tool")
        self.root.state('zoomed')  # Start maximized
        
        self.select_button = tk.Button(root, text="Select Directory", command=self.select_directory)
        self.select_button.pack(pady=20)
        
        self.canvas_frame = tk.Frame(root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, width=800, height=500)  # Adjust height to show more images
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.file_paths = []
        self.name_counters = {}
        self.selected_files = []
        self.image_refs = []  # Keep references to images to prevent garbage collection
        self.image_ids = {}  # Store image IDs to update selection visuals
        self.text_ids = {}  # Store text IDs to update selection order
        self.name_labels = {}  # Store name labels to display new names
        self.last_selected_index = None  # Track the last selected index for shift-click

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(fill=tk.X, pady=10)

        self.deselect_button = tk.Button(self.button_frame, text="Deselect All", command=self.deselect_all)
        self.deselect_button.pack(side=tk.LEFT, padx=10)

        self.rename_button = tk.Button(self.button_frame, text="Rename Selected Files", command=self.rename_selected_files)
        self.rename_button.pack(side=tk.LEFT, padx=10, expand=True)

        self.switch_button = tk.Button(self.button_frame, text="Switch", command=self.switch_file_names)
        self.switch_button.pack(side=tk.RIGHT, padx=10)

        self.image_queue = queue.Queue()
        self.root.after(100, self.process_queue)

        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.canvas.bind('<MouseWheel>', self.on_mouse_wheel)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)  # Handle window close event
        self.renaming_in_progress = False

        # Bind keys
        self.root.bind('<Delete>', self.delete_selected_images)
        self.root.bind('<r>', self.rename_selected_images)
        self.root.bind('<Escape>', lambda e: self.deselect_all())  # Bind ESC key to deselect all

        # Initialize PyUpdater client
        self.client = Client(ClientConfig(), refresh=True)
        self.check_for_updates()

    def on_closing(self):
        if self.renaming_in_progress:
            messagebox.showwarning("Renaming in Progress", "Please wait until the renaming process is finished.")
        else:
            self.root.destroy()

    def select_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.load_images(directory)

    def load_images(self, directory):
        def load():
            self.file_paths = self.get_image_files(directory)
            for index, file_path in enumerate(self.file_paths):
                image = self.load_image(file_path)
                self.image_queue.put((file_path, image))
        
        threading.Thread(target=load).start()

    def get_image_files(self, directory):
        return [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]

    def load_image(self, file_path):
        image = Image.open(file_path)
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        try:
            exif = dict(image._getexif().items())
            if exif[orientation] == 3:
                image = image.rotate(180, expand=True)
            elif exif[orientation] == 6:
                image = image.rotate(270, expand=True)
            elif exif[orientation] == 8:
                image = image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            # cases: image don't have getexif
            pass
        image.thumbnail((200, 200))  # Resize image to slightly bigger thumbnail
        return ImageTk.PhotoImage(image)

    def process_queue(self):
        try:
            while True:
                file_path, image = self.image_queue.get_nowait()
                self.display_image(file_path, image)
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def display_image(self, file_path, image):
        self.image_refs.append(image)  # Keep a reference to the image
        index = self.file_paths.index(file_path)
        canvas_width = self.canvas.winfo_width()
        images_per_row = 7
        image_width = 200
        padding = (canvas_width - (images_per_row * image_width)) // (images_per_row + 1)
        x = (index % images_per_row) * (image_width + padding) + padding
        y = (index // images_per_row) * (image_width + padding) + padding
        image_id = self.canvas.create_image(x, y, anchor=tk.NW, image=image)
        self.image_ids[file_path] = image_id
        self.canvas.tag_bind(image_id, '<Button-1>', lambda e, path=file_path, idx=index: self.toggle_selection(path, idx, e.state))
        # Display existing name labels if any
        if file_path in self.name_labels:
            self.canvas.create_text(x + 100, y + 180, text=self.name_labels[file_path], fill="green", font=("Arial", 10, "bold"))
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.display_images()

    def on_mouse_wheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.display_images()

    def toggle_selection(self, file_path, index, state):
        # Ensure the file_path is updated to the current name
        current_path = self.file_paths[index]
        if self.last_selected_index is not None and state & 0x0001:  # Check if Shift key is pressed
            start = min(self.last_selected_index, index)
            end = max(self.last_selected_index, index)
            for i in range(start, end + 1):
                path = self.file_paths[i]
                if path and path not in self.selected_files:  # Ignore null spots
                    self.selected_files.append(path)
                    x, y = self.canvas.coords(self.image_ids[path])
                    text_id = self.canvas.create_text(x + 10, y + 10, text=str(len(self.selected_files)), fill="red", font=("Arial", 16, "bold"))
                    self.text_ids[path] = text_id
        else:
            if current_path in self.selected_files:
                index = self.selected_files.index(current_path)
                self.selected_files.remove(current_path)
                self.canvas.delete(self.text_ids[current_path])
                # Update the numbers for the remaining selected files
                for i in range(index, len(self.selected_files)):
                    self.canvas.itemconfig(self.text_ids[self.selected_files[i]], text=str(i + 1))
            else:
                self.selected_files.append(current_path)
                x, y = self.canvas.coords(self.image_ids[current_path])
                text_id = self.canvas.create_text(x + 10, y + 10, text=str(len(self.selected_files)), fill="red", font=("Arial", 16, "bold"))
                self.text_ids[current_path] = text_id
            self.last_selected_index = index
        print(f"Selected files: {self.selected_files}")

    def deselect_all(self):
        for file_path in self.selected_files:
            self.canvas.delete(self.text_ids[file_path])
        self.selected_files = []
        self.last_selected_index = None
        print("Deselected all files")

    def switch_file_names(self):
        if len(self.selected_files) == 2:
            file1, file2 = self.selected_files
            path1, path2 = os.path.dirname(file1), os.path.dirname(file2)
            base1, base2 = os.path.basename(file1), os.path.basename(file2)
            temp_name = "temp_switch_name"
            temp_path = os.path.join(path1, temp_name)
            os.rename(file1, temp_path)
            os.rename(file2, os.path.join(path1, base1))
            os.rename(temp_path, os.path.join(path2, base2))
            print(f"Switched {file1} and {file2}")
            # Update the name labels on the images
            x1, y1 = self.canvas.coords(self.image_ids[file1])
            x2, y2 = self.canvas.coords(self.image_ids[file2])
            if file1 in self.name_labels:
                self.canvas.delete(self.name_labels[file1])
            if file2 in self.name_labels:
                self.canvas.delete(self.name_labels[file2])
            name_label1 = self.canvas.create_text(x1 + 100, y1 + 180, text=base2, fill="green", font=("Arial", 10, "bold"))
            name_label2 = self.canvas.create_text(x2 + 100, y2 + 180, text=base1, fill="green", font=("Arial", 10, "bold"))
            self.name_labels[os.path.join(path2, base2)] = name_label1
            self.name_labels[os.path.join(path1, base1)] = name_label2
            # Update the image IDs to the new paths
            self.image_ids[os.path.join(path2, base2)] = self.image_ids.pop(file1)
            self.image_ids[os.path.join(path1, base1)] = self.image_ids.pop(file2)
            # Update the file paths in the file_paths list
            self.file_paths[self.file_paths.index(file1)] = os.path.join(path2, base2)
            self.file_paths[self.file_paths.index(file2)] = os.path.join(path1, base1)
            # Deselect and remove the order numbers
            for path in self.selected_files:
                self.canvas.delete(self.text_ids[path])
            self.selected_files = []  # Clear the selection after switching
        else:
            messagebox.showwarning("Switch Error", "Please select exactly 2 images to switch their file names.")

    def rename_selected_files(self):
        if not self.selected_files:
            messagebox.showwarning("No Selection", "No files selected for renaming.")
            return
        
        new_name = simpledialog.askstring("Input", "Enter new name for the selected group of files (without extension):")
        if new_name:
            self.renaming_in_progress = True
            for index, file_path in enumerate(self.selected_files):
                filename = os.path.basename(file_path)
                counter = 1
                new_filename = f"{new_name}_{counter}{os.path.splitext(filename)[1]}"
                new_path = os.path.join(os.path.dirname(file_path), new_filename)
                while os.path.exists(new_path):
                    counter += 1
                    new_filename = f"{new_name}_{counter}{os.path.splitext(filename)[1]}"
                    new_path = os.path.join(os.path.dirname(file_path), new_filename)
                os.rename(file_path, new_path)
                print(f"Renamed {filename} to {new_filename}")
                # Update the name label on the image
                x, y = self.canvas.coords(self.image_ids[file_path])
                if file_path in self.name_labels:
                    self.canvas.delete(self.name_labels[file_path])  # Remove the previous green text
                name_label = self.canvas.create_text(x + 100, y + 180, text=new_filename, fill="green", font=("Arial", 10, "bold"))
                self.name_labels[new_path] = name_label  # Update the name label reference
                # Remove the order number from the corner
                self.canvas.delete(self.text_ids[file_path])
                # Update the image ID to the new path
                self.image_ids[new_path] = self.image_ids.pop(file_path)
                # Update the file path in the file_paths list
                self.file_paths[self.file_paths.index(file_path)] = new_path
                # Update the text_ids to allow reselection
                self.text_ids[new_path] = self.text_ids.pop(file_path)
            self.selected_files = []  # Clear the selection after renaming
            self.renaming_in_progress = False
        else:
            print("Skipping group.")

    def delete_selected_images(self, event=None):
        for file_path in self.selected_files:
            x, y = self.canvas.coords(self.image_ids[file_path])
            self.canvas.delete(self.image_ids[file_path])
            self.canvas.delete(self.text_ids[file_path])
            if file_path in self.name_labels:
                self.canvas.delete(self.name_labels[file_path])
            self.file_paths[self.file_paths.index(file_path)] = None  # Keep a null slot
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
            # Put a big red "DEL" on top of where the image used to be
            self.canvas.create_text(x + 100, y + 100, text="DEL", fill="red", font=("Arial", 24, "bold"))
        self.selected_files = []
        self.last_selected_index = None  # Reset the last selected index

    def rename_selected_images(self, event=None):
        self.rename_selected_files()

    def check_for_updates(self):
        self.client.refresh()
        app_update = self.client.update_check(ClientConfig.APP_NAME, ClientConfig.APP_VERSION)
        if app_update is not None:
            app_update.download(background=False)
            if app_update.is_downloaded():
                app_update.extract_restart()
        else:
            self.check_github_release()

    def check_github_release(self):
        response = requests.get("https://api.github.com/repos/bburnsd/FileRenamer/releases/latest")
        if response.status_code == 200:
            latest_release = response.json()
            latest_version = latest_release["tag_name"]
            if version.parse(latest_version) > version.parse(ClientConfig.APP_VERSION):
                messagebox.showinfo("Update Available", f"A new version ({latest_version}) is available. Please update your application.")
            else:
                messagebox.showinfo("Up to Date", "You are using the latest version of the application.")
        else:
            messagebox.showerror("Update Check Failed", "Failed to check for updates on GitHub.")

class ClientConfig:
    PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC8aFS6fp2FD/OlNfjmJhUVflVTqKUPEsE2wIkxzgX+o"
    APP_NAME = "FileRenamer"
    APP_VERSION = "0.1.1"
    UPDATE_URLS = ["https://github.com/bburnsd/FileRenamer/releases/latest"]

# Create the main window
root = tk.Tk()
app = FileRenamerApp(root)

# Run the application
root.mainloop()
