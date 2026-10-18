.PHONY: help install test benchmark dashboard lint clean docker-build

help:
	@echo "Tripwire — Make Targets:"
	@echo "  make install    - Install package and dependencies"
	@echo "  make test       - Run all unit, integration, and security tests"
	@echo "  make benchmark  - Run 120-case evaluation benchmark"
	@echo "  make dashboard  - Launch Streamlit SecOps dashboard"
	@echo "  make clean      - Clean cache and temporary audit data"

install:
	pip install -r requirements.txt
	pip install -e .

test:
	python -m pytest -v

benchmark:
	python eval/run_benchmark.py

dashboard:
	streamlit run dashboard/app.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
