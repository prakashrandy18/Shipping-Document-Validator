/**
 * Shipping Document Comparator - Frontend JavaScript
 * Handles 3-document upload, preview/edit, comparison, and LEARNING
 */

// Global state
let extractedData = null;
let currentStep = 1;

document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    loadLearningStats();
});

function initializeApp() {
    // Setup file inputs and drag-drop for all 3 documents
    setupFileInput('docA', 'dropzoneA', 'fileNameA');
    setupFileInput('docB', 'dropzoneB', 'fileNameB');
    setupFileInput('docC', 'dropzoneC', 'fileNameC');

    // Form submissions
    document.getElementById('uploadForm').addEventListener('submit', handleExtract);

    // Button handlers
    document.getElementById('backToUploadBtn').addEventListener('click', goToStep1);
    document.getElementById('compareBtn').addEventListener('click', handleCompare);
    document.getElementById('newComparisonBtn').addEventListener('click', resetAll);
}

function setupFileInput(inputId, dropzoneId, fileNameId) {
    const input = document.getElementById(inputId);
    const dropzone = document.getElementById(dropzoneId);

    input.addEventListener('change', (e) => {
        const file = e.target.files[0];
        updateFileName(file, fileNameId, dropzone);
    });

    // Drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
    });

    dropzone.addEventListener('drop', (e) => {
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            const dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            updateFileName(file, fileNameId, dropzone);
        }
    }, false);
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function updateFileName(file, fileNameId, dropzone) {
    const fileNameEl = document.getElementById(fileNameId);
    if (file) {
        fileNameEl.textContent = file.name;
        fileNameEl.classList.add('selected');
        dropzone.classList.add('has-file');
    } else {
        fileNameEl.textContent = 'No file selected';
        fileNameEl.classList.remove('selected');
        dropzone.classList.remove('has-file');
    }
}

// Step navigation
function goToStep(step) {
    currentStep = step;

    // Update step indicator
    document.querySelectorAll('.step').forEach((el, idx) => {
        el.classList.remove('active', 'completed');
        if (idx + 1 < step) el.classList.add('completed');
        if (idx + 1 === step) el.classList.add('active');
    });

    // Show/hide sections
    document.getElementById('uploadSection').classList.toggle('hidden', step !== 1);
    document.getElementById('reviewSection').classList.toggle('hidden', step !== 2);
    document.getElementById('resultsSection').classList.toggle('hidden', step !== 3);
}

function goToStep1() {
    goToStep(1);
}

// Step 1: Extract values from PDFs
async function handleExtract(e) {
    e.preventDefault();

    const docA = document.getElementById('docA').files[0];
    const docB = document.getElementById('docB').files[0];
    const docC = document.getElementById('docC').files[0];
    const extractBtn = document.getElementById('extractBtn');

    // Validate at least 2 files
    const uploadedCount = [docA, docB, docC].filter(f => f).length;
    if (uploadedCount < 2) {
        showNotification('Please upload at least 2 PDF documents', 'error');
        return;
    }

    // Show loading
    extractBtn.classList.add('loading');
    extractBtn.disabled = true;

    try {
        const formData = new FormData();
        if (docA) formData.append('doc_a', docA);
        if (docB) formData.append('doc_b', docB);
        if (docC) formData.append('doc_c', docC);

        const response = await fetch('/preview', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            extractedData = data.documents;
            populateReviewTable(data.documents);

            if (data.warning) {
                showNotification(data.warning, 'error'); // Use red for visibility
            }

            goToStep(2);
        } else {
            showNotification(data.error || 'Failed to extract values', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('An error occurred during extraction', 'error');
    } finally {
        extractBtn.classList.remove('loading');
        extractBtn.disabled = false;
    }
}

// Populate the review table
function populateReviewTable(documents) {
    const tbody = document.getElementById('reviewTableBody');
    tbody.innerHTML = '';

    // Update headers with filenames
    if (documents.doc_a) {
        document.getElementById('headerA').innerHTML = `OBL<br><small>${documents.doc_a.filename}</small>`;
    }
    if (documents.doc_b) {
        document.getElementById('headerB').innerHTML = `PKL<br><small>${documents.doc_b.filename}</small>`;
    }
    if (documents.doc_c) {
        document.getElementById('headerC').innerHTML = `INV<br><small>${documents.doc_c.filename}</small>`;
    }

    // Get all field keys - only the 3 fields user needs
    const fieldKeys = ['cartons', 'gross_weight', 'cbm'];
    const fieldLabels = {
        'cartons': 'Cartons (CTN)',
        'gross_weight': 'Gross Weight (KGS)',
        'cbm': 'Volume (CBM)'
    };

    fieldKeys.forEach(fieldKey => {
        const row = document.createElement('tr');

        // Field name cell
        row.innerHTML = `<td class="field-name">${fieldLabels[fieldKey]}</td>`;

        // Value cells for each document
        ['doc_a', 'doc_b', 'doc_c'].forEach(docKey => {
            const cell = document.createElement('td');
            cell.className = 'value-cell';

            const doc = documents[docKey];
            if (doc && doc.details && doc.details[fieldKey]) {
                const detail = doc.details[fieldKey];
                const confidence = detail.confidence || 0;
                const value = detail.value || '';

                let inputClass = 'value-input';
                let confidenceClass = 'low';
                let confidenceText = 'Not found';
                let sourceBadge = '';

                if (value) {
                    // Show source badge
                    const source = detail.source || 'regex';
                    if (source === 'learned_pattern' || source === 'learned') {
                        sourceBadge = '<span class="source-badge learned">🎓 Learned</span>';
                    } else {
                        sourceBadge = '<span class="source-badge regex">📝 Pattern</span>';
                    }

                    if (confidence >= 0.9) {
                        inputClass += ' high-confidence';
                        confidenceClass = 'high';
                        confidenceText = 'High confidence';
                    } else if (confidence >= 0.7) {
                        inputClass += ' medium-confidence';
                        confidenceClass = 'medium';
                        confidenceText = 'Medium confidence';
                    } else {
                        inputClass += ' low-confidence';
                        confidenceClass = 'low';
                        confidenceText = 'Low confidence';
                    }
                } else {
                    inputClass += ' no-value';
                }

                cell.innerHTML = `
                    <input type="text" 
                           class="${inputClass}" 
                           data-doc="${docKey}" 
                           data-field="${fieldKey}"
                           data-doc-id="${doc.doc_id || ''}"
                           value="${value || ''}"
                           placeholder="Enter value">
                    <div class="confidence-indicator">
                        <span class="confidence-dot ${confidenceClass}"></span>
                        <span class="confidence-text">${confidenceText}</span>
                        ${sourceBadge}
                    </div>
                    ${value ? `<button class="learn-btn" onclick="learnValue('${docKey}', '${fieldKey}', '${doc.doc_id}')">✅ Correct</button>` : ''}
                `;
            } else {
                cell.innerHTML = `
                    <input type="text" 
                           class="value-input no-value" 
                           data-doc="${docKey}" 
                           data-field="${fieldKey}"
                           value=""
                           placeholder="N/A"
                           disabled>
                    <div class="confidence-indicator">
                        <span class="confidence-dot low"></span>
                        <span class="confidence-text">No document</span>
                    </div>
                `;
            }

            row.appendChild(cell);
        });

        tbody.appendChild(row);
    });
}

// Learn from user feedback
async function learnValue(docKey, fieldKey, docId) {
    const input = document.querySelector(`input[data-doc="${docKey}"][data-field="${fieldKey}"]`);
    const value = input.value.trim();

    if (!value || !docId) {
        showNotification('Cannot learn: missing value or document ID', 'error');
        return;
    }

    try {
        const response = await fetch('/learn', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                doc_id: docId,
                field: fieldKey,
                value: value
            })
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✅ Pattern learned! System will remember this.', 'success');
            // Reload learning stats
            loadLearningStats();
        } else {
            showNotification(data.error || 'Failed to learn pattern', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('Error learning pattern', 'error');
    }
}

// Load and display learning stats
async function loadLearningStats() {
    try {
        const response = await fetch('/learning/stats');
        const data = await response.json();

        if (data.success && data.stats) {
            // You can display stats in the UI if desired
            console.log('Learning Stats:', data.stats);
        }
    } catch (error) {
        console.log('Could not load learning stats');
    }
}

// Step 2: Compare values
async function handleCompare() {
    const compareBtn = document.getElementById('compareBtn');

    // Gather values from inputs
    const confirmedValues = {
        doc_a: {},
        doc_b: {},
        doc_c: {}
    };

    document.querySelectorAll('.value-input').forEach(input => {
        const docKey = input.dataset.doc;
        const fieldKey = input.dataset.field;
        const value = input.value.trim();

        if (!confirmedValues[docKey][fieldKey]) {
            confirmedValues[docKey][fieldKey] = {};
        }
        confirmedValues[docKey][fieldKey] = {
            value: value || null,
            label: extractedData?.[docKey]?.details?.[fieldKey]?.label || fieldKey
        };
    });

    // Show loading
    compareBtn.classList.add('loading');
    compareBtn.disabled = true;

    try {
        const response = await fetch('/compare', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(confirmedValues)
        });

        const data = await response.json();

        if (data.success) {
            displayResults(data.results);
            goToStep(3);
        } else {
            showNotification(data.error || 'Comparison failed', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('An error occurred during comparison', 'error');
    } finally {
        compareBtn.classList.remove('loading');
        compareBtn.disabled = false;
    }
}

// Display comparison results
function displayResults(results) {
    const statusBadge = document.getElementById('statusBadge');
    const summaryContainer = document.getElementById('resultsSummary');
    const tbody = document.getElementById('comparisonTableBody');

    // Count statuses
    let matchCount = 0;
    let mismatchCount = 0;
    let warningCount = 0;

    results.comparisons.forEach(comp => {
        if (comp.status === 'success') matchCount++;
        else if (comp.status === 'error') mismatchCount++;
        else warningCount++;
    });

    // Update status badge
    if (results.all_match && mismatchCount === 0) {
        statusBadge.className = 'status-badge success';
        statusBadge.innerHTML = '<span class="status-icon">✅</span><span class="status-text">All Values Match!</span>';
    } else if (mismatchCount > 0) {
        statusBadge.className = 'status-badge error';
        statusBadge.innerHTML = `<span class="status-icon">❌</span><span class="status-text">${mismatchCount} Mismatch${mismatchCount > 1 ? 'es' : ''} Found</span>`;
    } else {
        statusBadge.className = 'status-badge partial';
        statusBadge.innerHTML = '<span class="status-icon">⚠️</span><span class="status-text">Partial Match</span>';
    }

    // Summary cards
    summaryContainer.innerHTML = `
        <div class="summary-card success">
            <div class="number">${matchCount}</div>
            <div class="label">Matches</div>
        </div>
        <div class="summary-card error">
            <div class="number">${mismatchCount}</div>
            <div class="label">Mismatches</div>
        </div>
        <div class="summary-card warning">
            <div class="number">${warningCount}</div>
            <div class="label">Warnings</div>
        </div>
    `;

    // Comparison table
    tbody.innerHTML = '';
    results.comparisons.forEach(comp => {
        const row = document.createElement('tr');

        const valA = comp.values.doc_a;
        const valB = comp.values.doc_b;
        const valC = comp.values.doc_c;

        let valueClass = '';
        let statusIcon = '';

        if (comp.status === 'success') {
            valueClass = 'match-value';
            statusIcon = '✅';
        } else if (comp.status === 'error') {
            valueClass = 'mismatch-value';
            statusIcon = '❌';
        } else if (comp.status === 'partial') {
            valueClass = 'match-value';
            statusIcon = '⚠️';
        } else {
            valueClass = 'missing-value';
            statusIcon = '⚠️';
        }

        row.innerHTML = `
            <td class="field-name">${comp.field}</td>
            <td class="value ${valA ? valueClass : 'missing-value'}">${valA || 'N/A'}</td>
            <td class="value ${valB ? valueClass : 'missing-value'}">${valB || 'N/A'}</td>
            <td class="value ${valC ? valueClass : 'missing-value'}">${valC || 'N/A'}</td>
            <td class="status"><span class="status-icon">${statusIcon}</span></td>
        `;

        tbody.appendChild(row);
    });
}

// Reset and start new comparison
function resetAll() {
    extractedData = null;

    // Clear file inputs
    ['docA', 'docB', 'docC'].forEach((id, idx) => {
        const input = document.getElementById(id);
        const dropzoneId = `dropzone${['A', 'B', 'C'][idx]}`;
        const fileNameId = `fileName${['A', 'B', 'C'][idx]}`;

        input.value = '';
        document.getElementById(fileNameId).textContent = 'No file selected';
        document.getElementById(fileNameId).classList.remove('selected');
        document.getElementById(dropzoneId).classList.remove('has-file');
    });

    // Reset table headers
    document.getElementById('headerA').innerHTML = 'OBL';
    document.getElementById('headerB').innerHTML = 'PKL';
    document.getElementById('headerC').innerHTML = 'INV';

    goToStep(1);
}

// Notification helper
function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}
