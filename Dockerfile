# Use NVIDIA CUDA base image
FROM sulfurheron/nvidia-cuda:9.0-cudnn7-devel-ubuntu16.04-2018-06-08

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set home to the user's home directory and ensure CUDA is in the PATH
ENV HOME=/home/user \
    CUDA_HOME=/usr/local/cuda \
    PATH=/home/user/.local/bin:$PATH \
    LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH} \
    LIBRARY_PATH=${CUDA_HOME}/lib64/stubs:${LIBRARY_PATH} \
    PYTHONPATH=$HOME/app \
    PYTHONUNBUFFERED=1 \
    SYSTEM=spaces 

# Set CUDA environment variables
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Add NVIDIA GPG key
RUN apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1604/x86_64/3bf863cc.pub

# Install required packages for building Python and OpenCV
RUN apt-get update && \
    apt-get install -y build-essential libssl-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl unzip \
    libglib2.0-0 libglib2.0-dev libsm6 libxext6 libxrender-dev && \
    rm -rf /var/lib/apt/lists/*

# Remove existing CuDNN libraries if they exist
RUN apt-get remove -y libcudnn7 libcudnn7-dev || true

# Download and install the desired version of CuDNN
RUN wget https://developer.download.nvidia.com/compute/redist/cudnn/v7.0.4/Ubuntu16_04-x64/libcudnn7_7.0.4.31-1+cuda9.0_amd64.deb -O /tmp/libcudnn7.deb && \
    wget https://developer.download.nvidia.com/compute/redist/cudnn/v7.0.4/Ubuntu16_04-x64/libcudnn7-dev_7.0.4.31-1+cuda9.0_amd64.deb -O /tmp/libcudnn7-dev.deb && \
    dpkg -i /tmp/libcudnn7.deb && \
    dpkg -i /tmp/libcudnn7-dev.deb && \
    rm /tmp/libcudnn7.deb /tmp/libcudnn7-dev.deb

RUN apt-get update && apt-get install -y --no-install-recommends \
    cuda-drivers && \
    rm -rf /var/lib/apt/lists/*

# Download and install Python 3.6.15
RUN curl -O https://www.python.org/ftp/python/3.6.15/Python-3.6.15.tgz && \
    tar -xzf Python-3.6.15.tgz && \
    cd Python-3.6.15 && \
    ./configure --enable-optimizations && \
    make altinstall && \
    cd .. && \
    rm -rf Python-3.6.15 Python-3.6.15.tgz

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set the working directory to the user's home directory
WORKDIR $HOME/app

USER root

# Try and run pip command after setting the user with `USER user` to avoid permission issues with Python
RUN python3.6 -m ensurepip && \
    python3.6 -m pip install --no-cache-dir --upgrade pip

# Switch back to the "user" user
USER user

# Install required Python packages
RUN python3.6 -m pip install --no-cache-dir tensorflow_gpu==1.5.0 && \
    python3.6 -m pip install --no-cache-dir keras==2.2.4 && \
    python3.6 -m pip install --no-cache-dir opencv-python==3.4.2.17 && \
    python3.6 -m pip install --no-cache-dir numpy==1.15.4 && \
    python3.6 -m pip install --no-cache-dir numba==0.39.0 && \
    python3.6 -m pip install --no-cache-dir scipy==1.1.0 && \
    python3.6 -m pip install --no-cache-dir scikit-image==0.13.0 && \
    python3.6 -m pip install --no-cache-dir scikit-learn==0.22.2 && \
    python3.6 -m pip install --no-cache-dir llvmlite==0.32.1

# Fix h5py version for compatibility
RUN python3.6 -m pip uninstall -y h5py && \
    python3.6 -m pip install --no-cache-dir h5py==2.10.0

# Copy the "code" folder contents into the working directory
COPY --chown=user code/. $HOME/app/

# Install Flask
RUN python3.6 -m pip install Flask

# Copy the Flask application code into the container
COPY --chown=user flask_app.py $HOME/app/flask_app.py

# Log the contents of the $HOME/app directory
RUN ls -la $HOME/app/

# Expose the port for the Flask app
EXPOSE 5000

# Launch the Flask application
CMD ["python3.6", "flask_app.py"]
