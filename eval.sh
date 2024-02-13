#!/bin/bash

# Check if the data/ directory exists
if [ -d "data/" ]; then
    # Delete all .pkl files in the data/ directory
    rm data/*.pkl
fi

# Step 2: Delete out.txt if it exists
if [ -f "out.txt" ]; then
    rm "out.txt"
fi

# Repeat evaluation as necessary
while true; do
    # Run evaluation.py and append output to out.txt as well as display it
    python -u evaluation.py 2>&1 | tee -a out.txt

    # Capture the exit status of python script
    exit_status=${PIPESTATUS[0]}

    # Check exit status
    if [ $exit_status -ne 1 ]; then
        # If exit status is not 1, break the loop
        break
    fi

    # If this program returns code 1, the loop continues, repeating the evaluation
done
