document.addEventListener('DOMContentLoaded', () => {
    const POLL_INTERVAL = 30000; // 30 seconds
    
    // DOM Elements
    const statEdits = document.getElementById('stat-edits');
    const statEditors = document.getElementById('stat-editors');
    const statUploads = document.getElementById('stat-uploads');
    const statBytes = document.getElementById('stat-bytes');
    
    const leaderboardBody = document.getElementById('leaderboardBody');
    const editorInput = document.getElementById('editorInput');
    const addEditorBtn = document.getElementById('addEditorBtn');
    const toast = document.getElementById('toast');

    // State
    let currentData = [];

    // Format numbers
    const formatNum = (num) => new Intl.NumberFormat().format(num);
    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 B';
        const sign = bytes < 0 ? '-' : '+';
        bytes = Math.abs(bytes);
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${sign} ${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
    };

    // Update Top Stats
    const updateStats = (stats) => {
        statEdits.textContent = formatNum(stats.total_edits);
        statEditors.textContent = formatNum(stats.total_editors);
        statUploads.textContent = formatNum(stats.total_uploads);
        statBytes.textContent = formatBytes(stats.bytes_added);
    };

    // Render Leaderboard
    const renderLeaderboard = (leaderboard) => {
        // Simple diff check to avoid unnecessary re-renders (prevents flickering)
        if (JSON.stringify(currentData) === JSON.stringify(leaderboard)) {
            return;
        }
        currentData = leaderboard;

        leaderboardBody.innerHTML = '';
        
        if (leaderboard.length === 0) {
            leaderboardBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No edits recorded yet. Waiting for participants...</td></tr>`;
            return;
        }

        leaderboard.forEach(entry => {
            const row = document.createElement('tr');
            
            // Add top 3 classes
            if (entry.rank <= 3) {
                row.classList.add(`rank-${entry.rank}`);
            }

            row.innerHTML = `
                <td>#${entry.rank}</td>
                <td><a href="https://commons.wikimedia.org/wiki/User:${encodeURIComponent(entry.username)}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 600;">${entry.username}</a></td>
                <td>${formatNum(entry.total_edits)}</td>
                <td>${formatNum(entry.file_uploads)}</td>
                <td style="color: var(--accent-green)">${formatBytes(entry.bytes_changed)}</td>
            `;
            leaderboardBody.appendChild(row);
        });
    };

    // Fetch Live Data
    const fetchLiveStats = async () => {
        try {
            const res = await fetch('/api/live-stats');
            if (!res.ok) throw new Error("Failed to fetch");
            const data = await res.json();
            
            updateStats(data.global_stats);
            renderLeaderboard(data.leaderboard);
        } catch (err) {
            console.error("Live polling error:", err);
        }
    };

    // Show Toast Notification
    const showToast = (message, isError = false) => {
        toast.textContent = message;
        toast.style.borderLeftColor = isError ? '#ef4444' : 'var(--accent-green)';
        toast.classList.remove('hidden');
        
        // Small delay to ensure display:block applies before opacity transition
        setTimeout(() => toast.classList.add('show'), 10);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.classList.add('hidden'), 300);
        }, 3000);
    };

    // Add Editor Handler
    const handleAddEditor = async () => {
        const username = editorInput.value.trim();
        if (!username) {
            showToast("Please enter a username", true);
            return;
        }

        addEditorBtn.disabled = true;
        addEditorBtn.textContent = 'Adding...';

        try {
            const res = await fetch('/api/editors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            
            const data = await res.json();
            
            if (!res.ok) {
                throw new Error(data.detail || "Failed to add editor");
            }
            
            showToast(`Added ${username}. Backfilling past edits...`);
            editorInput.value = '';
            fetchLiveStats(); // Immediate update
        } catch (err) {
            showToast(err.message, true);
        } finally {
            addEditorBtn.disabled = false;
            addEditorBtn.textContent = 'Register Editor';
        }
    };

    // Event Listeners
    addEditorBtn.addEventListener('click', handleAddEditor);
    editorInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleAddEditor();
    });

    // Start Polling
    fetchLiveStats(); // Initial fetch
    setInterval(fetchLiveStats, POLL_INTERVAL);
});
