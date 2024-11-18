from flask import Flask, request, send_from_directory, render_template, Response
import os
import subprocess
import threading
import time
import tempfile
import queue  # For managing the task queue

app = Flask(__name__)

# Set the upload and output folders to be within $HOME/app
UPLOAD_FOLDER = os.path.join(os.environ['HOME'], 'app', 'uploads')
OUTPUT_FOLDER = os.path.join(os.environ['HOME'], 'app', 'outputs')

# Ensure the upload and output directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

task_queue = queue.Queue()

def worker():
    """Worker function that processes tasks from the task_queue."""
    while worker_running:
        task_id = task_queue.get()  # This will block until a task is available
        if task_id is None:  # Check for explicit termination signal
            continue
        try:
            process_task(task_id)
        except Exception as e:
            print(f"Error processing task {task_id}: {e}")
        finally:
            task_queue.task_done()

# Start the worker thread in the background
thread = threading.Thread(target=worker, daemon=True)
thread.start()
worker_running = True  # Flag to keep the worker running


def process_task(task_id):
    """Process the task (run segmentation) and monitor progress."""
    # Here, task_id could be an identifier to keep track of which task is being processed
    print(f"Processing task {task_id}...")
    
    # Run the segmentation process for this task
    # We can use the existing monitor_logs function here
    # You can pass task_id into monitor_logs if necessary for logging
    segment_script_path = os.path.join(os.environ['HOME'], 'app', 'segment.py')
    filename = app.config.get('uploaded_file')
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    log_file_path = tempfile.mktemp(prefix="segmentation_", suffix=f"_{task_id}.log")

    # Run the task monitoring in the background
    monitor_logs(file_path, log_file_path, task_id)  # This will handle progress updates


@app.route('/')
def upload_form():
    return '''
    <html>
        <body>
            <h1>Upload an Image</h1>
            <form id="uploadForm" action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="image/*" id="fileInput" required>
            </form>
            <div id="MyDivToUpdate" style="width: 100%; height: 100px; border: 1px solid black;">
                This is the div to be updated.
            </div>
            <script>
                // Automatically submit the form when a file is selected
                document.getElementById('fileInput').addEventListener('change', function() {
                   // Change the background color of the div
                    var myDiv = document.getElementById('MyDivToUpdate');
                    myDiv.style.backgroundColor = 'red';
                    
                    // Update the text content of the div
                    myDiv.innerHTML = 'Loading your image...';

                    // Submit the form
                    document.getElementById('uploadForm').submit();
                });
            </script>
        </body>
    </html>
    '''

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'

    # Save the uploaded file
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    print(f"File saved to: {file_path}")  # Debugging line

    # Store the filename in a global config for simplicity
    app.config['uploaded_file'] = file.filename

    return '''
    <html>
        <body>
            <h1>Uploaded Image</h1>
            ''' + (f'<img src="/uploads/{file.filename}" alt="Uploaded Image" style="max-width: 500px;">') + '''<br>
            <h2>Change Image</h2>
            <form id="reuploadForm" action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="image/*" id="fileInput" required>
            </form>
            <script>
                // Automatically submit the form when a file is selected
                document.getElementById('fileInput').addEventListener('change', function() {
                    document.getElementById('reuploadForm').submit();
                });
            </script>
            <h1>Run Segmentation</h1>
            <form action="/run" method="post">
                <input type="submit" value="Run Segmentation">
            </form>
        </body>
    </html>
    '''

# Progress tracking
progress = {}

def monitor_logs(file_path, log_file_path, task_id):
    """Monitor the logs of the segmentation script and update progress."""
    segment_script_path = os.path.join(os.environ['HOME'], 'app', 'segment.py')

    # List of expected log messages for tracking
    log_messages = [
        "begin load", "Loading weights", "Loading image...", "Image loaded, starting processing...",
        "Starting segmentation...", "Starting go_transposed_vector...", "Starting go_flipped_vector...",
        "Completed go_flipped_vector.", "Starting go_flipped_vector...", "Completed go_flipped_vector.",
        "Completed go_transposed_vector.", "Starting get_fill...", "Completed get_fill.",
        "Starting get_fill...", "Completed get_fill.", "Starting get_fill...", "Completed get_fill.",
        "Starting up_fill...", "Completed up_fill.", "Segmentation completed", "Saving output images...",
        "./current_skeleton.png", "./current_region.png", "./current_flatten.png", "Processing complete!"
    ]

    # Initialize task-specific progress tracking
    progress[task_id] = {'current': 0, 'total': len(log_messages)}

    # Open the log file in append mode to write the new logs
    with open(log_file_path, 'a') as log_file:
        message_counts = {msg: 0 for msg in log_messages}

        with subprocess.Popen(
            ['python3.6', segment_script_path, file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            cwd=OUTPUT_FOLDER  # Run the script in the output folder
        ) as proc:
            for line in proc.stdout:
                log_file.write(line)
                log_file.flush()

                for i, msg in enumerate(log_messages):
                    if msg in line:
                        message_counts[msg] += 1
                        progress[task_id]['current'] = i + 1 + message_counts[msg]
                        break

                # Detect and store generated file messages
                if "./current_skeleton.png" in line:
                    app.config['output_skeleton'] = "current_skeleton.png"
                elif "./current_region.png" in line:
                    app.config['output_region'] = "current_region.png"
                elif "./current_flatten.png" in line:
                    app.config['output_flatten'] = "current_flatten.png"

        # Ensure progress is complete at the end
        progress[task_id]['current'] = progress[task_id]['total']


@app.route('/progress/<task_id>')
def progress_stream(task_id):
    """Stream progress updates for a specific task."""
    def generate_progress():
        while progress.get(task_id, {}).get('current', 0) < progress.get(task_id, {}).get('total', 0):
            yield f"data: {progress[task_id]['current']}/{progress[task_id]['total']}\n\n"
            time.sleep(0.5)  # Adjust for smoother updates
        yield f"data: {progress[task_id]['total']}/{progress[task_id]['total']}\n\n"  # Send final update

    return Response(generate_progress(), content_type='text/event-stream')

@app.route('/run', methods=['POST'])
def run_segmentation():
    filename = app.config.get('uploaded_file')
    if not filename:
        return 'No file uploaded. Please upload an image first.'

    # Generate a unique task ID for this request
    task_id = str(int(time.time()))  # Using current timestamp as task ID

    # Add the task to the queue for processing
    task_queue.put(task_id)

    # Display progress page
    return '''
    <html>
        <body>
            <h1>Running Segmentation...</h1>
            <progress id="progressBar" value="0" max="25"></progress>
            <span id="stepCounter">Step 0/25</span> <!-- Display the step counter -->
            <script>
                const progressBar = document.getElementById('progressBar');
                const stepCounter = document.getElementById('stepCounter');
                const evtSource = new EventSource('/progress/''' + (f'{task_id}') + '''');
                
                evtSource.onmessage = function(event) {
                    const [current, total] = event.data.split('/');
                    progressBar.value = current;
                    stepCounter.textContent = `Step ${current}/${total}`;  // Update the step counter
                    if (current == total) {
                        evtSource.close();
                        window.location.href = "/results";
                    }
                };
            </script>
        </body>
    </html>
    '''

@app.route('/results')
def results_page():
    filename = app.config.get('uploaded_file')
    output_skeleton = app.config.get('output_skeleton', 'current_skeleton.png')
    output_region = app.config.get('output_region', 'current_region.png')
    output_flatten = app.config.get('output_flatten', 'current_flatten.png')

    return f'''
    <html>
        <body>
            <h1>Segmentation Completed</h1>
            <h1>Download Output Images</h1>
            <a href="/download/{output_skeleton}">Download Skeleton</a><br>
            <a href="/download/{output_region}">Download Region</a><br>
            <a href="/download/{output_flatten}">Download Flatten</a><br>
            <h1>Uploaded Image</h1>
            <img src="/uploads/{filename}" alt="Uploaded Image" style="max-width: 500px;">
            <img src="/download/{output_region}" alt="Regioned Image" style="max-width: 500px;">
            <img src="/download/{output_flatten}" alt="Flatten Image" style="max-width: 500px;">
        </body>
    </html>
    '''

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
