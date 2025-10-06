document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const promptInput = document.getElementById('prompt-input');
    const chatWindow = document.getElementById('chat-window');
    const refreshButton = document.getElementById('refresh-memories');
    const memoriesList = document.getElementById('memories-list');
    const sessionIdInput = document.getElementById('session_id');
    const clearMemoriesButton = document.getElementById('clear-memories');
    const consolidateButton = document.getElementById('consolidate-memories'); 

    const getUserId = () => {
        let userId = localStorage.getItem('user_id');
        if (!userId) {
            userId = `user_${crypto.randomUUID()}`;
            localStorage.setItem('user_id', userId);
        }
        return userId;
    };

    const getSessionHistory = () => {
        const history = localStorage.getItem('session_history');
        return history ? JSON.parse(history) : [];
    };

    const trackSessionId = (sessionId) => {
        let history = getSessionHistory();
        if (!history.includes(sessionId)) {
            history.push(sessionId);
            localStorage.setItem('session_history', JSON.stringify(history));
        }
    };

    const getSessionId = () => {
        let sessionId = sessionStorage.getItem('session_id');
        if (!sessionId) {
            sessionId = crypto.randomUUID();
            sessionStorage.setItem('session_id', sessionId);
            trackSessionId(sessionId);
        }
        return sessionId;
    };

    const currentSessionId = getSessionId();
    sessionIdInput.value = currentSessionId;

    const addMessage = (role, text) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        contentDiv.textContent = text;
        messageDiv.appendChild(contentDiv);
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        return contentDiv;
    };

    async function consolidateUserMemories() {
        const userId = getUserId();
        const sessionIds = getSessionHistory();

        if (sessionIds.length === 0) {
            alert('No sessions to consolidate.');
            return;
        }
        
        console.log(`Consolidating ${sessionIds.length} sessions for user ${userId}...`);
        alert(`Consolidating ${sessionIds.length} sessions. Check the developer console for results.`);

        try {
            const response = await fetch('/consolidate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    session_ids: sessionIds
                })
            });
            const result = await response.json();
            console.log('Consolidation complete:', result);
        } catch (error) {
            console.error('Consolidation failed:', error);
            alert('Consolidation failed. See console for details.');
        }
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const prompt = promptInput.value;
        if (!prompt) return;

        const sessionId = getSessionId();
        const userId = getUserId();

        addMessage('user', prompt);
        promptInput.value = '';
        const assistantMessageContent = addMessage('assistant', '...');
        assistantMessageContent.textContent = '';

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, prompt: prompt })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (line.startsWith('data:')) {
                        const data = JSON.parse(line.substring(5));
                        if (data.token) {
                            assistantMessageContent.textContent += data.token;
                            chatWindow.scrollTop = chatWindow.scrollHeight;
                        }
                        if (data.status === 'done') {
                            fetchMemories();
                            return;
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error during generation:', error);
            assistantMessageContent.textContent = 'Error: Could not get response.';
        }
    });

    const fetchMemories = async () => {
        const sessionId = getSessionId();
        if (!sessionId) return;

        try {
            const response = await fetch(`/memories?limit=10&session_id=${sessionId}`);
            const memories = await response.json();
            memoriesList.innerHTML = '';
            memories.forEach(mem => {
                const item = document.createElement('div');
                item.className = 'memory-item';
                item.textContent = mem.text;
                memoriesList.appendChild(item);
            });
        } catch (error) {
            console.error("Failed to fetch memories", error);
        }
    };

    clearMemoriesButton.addEventListener('click', async () => {
        const sessionId = getSessionId();
        if (!sessionId) { alert('No session ID found.'); return; }
        if (!confirm('Are you sure you want to delete all memories for this session?')) { return; }

        try {
            const response = await fetch(`/memories/${sessionId}`, { method: 'DELETE' });
            if (!response.ok) { throw new Error('Failed to clear memories.'); }
            fetchMemories();
        } catch (error) {
            console.error('Error clearing memories:', error);
            alert('Could not clear memories.');
        }
    });
    
    consolidateButton.addEventListener('click', consolidateUserMemories);

    refreshButton.addEventListener('click', fetchMemories);
    fetchMemories();
});