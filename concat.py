import os

def concatenate_python_files(output_file, root_dir, exclude_dirs=None):
    """
    Concatenates all Python files in the specified directory recursively into a single file.

    :param output_file: Path to the output file where concatenated content will be written.
    :param root_dir: Root directory to start searching for Python files.
    :param exclude_dirs: List of directories to exclude.
    """
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', '.git', '.venv', 'build', 'dist', '.idea', '.vscode']

    with open(output_file, 'w') as output:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Remove excluded directories from the traversal
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

            for filename in filenames:
                if filename.endswith('.py'):
                    file_path = os.path.join(dirpath, filename)
                    if os.path.getsize(file_path) > 0:  # Skip empty files
                        output.write(f"# File: {file_path}\n")
                        try:
                            with open(file_path, 'r', encoding='utf-8') as file:
                                content = file.read()
                                output.write(content + '\n\n')
                        except Exception as e:
                            output.write(f"# Error reading {file_path}: {e}\n\n")

if __name__ == "__main__":
    output_file = "concatenated_python_files.py"
    root_dir = os.getcwd()  # Change this to the desired root directory if needed
    concatenate_python_files(output_file, root_dir)
    print(f"All Python files have been concatenated into {output_file}.")
