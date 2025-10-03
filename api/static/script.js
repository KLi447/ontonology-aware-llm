document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const promptInput = document.getElementById('prompt-input');
    const chatWindow = document.getElementById('chat-window');
    const refreshButton = document.getElementById('refresh-memories');
    const memoriesList = document.getElementById('memories-list');

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

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const prompt = promptInput.value;
        if (!prompt) return;

        const sessionId = document.getElementById('session_id').value;
        if (!sessionId) {
            alert('Please enter a Session ID');
            return;
        }

        addMessage('user', prompt);
        promptInput.value = '';

        const assistantMessageContent = addMessage('assistant', '...');
        assistantMessageContent.textContent = '';

        try {
            const eventSource = new EventSource(`/generate?session_id=${encodeURIComponent(sessionId)}&prompt=${encodeURIComponent(prompt)}`, {
                method: 'POST',
            });
            
            const response = await fetch('/generate', {
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
        const sessionId = document.getElementById('session_id').value;
        if (!sessionId) return;
        
        try {
            const response = await fetch(`/memories?limit=10`);
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
    
    refreshButton.addEventListener('click', fetchMemories);
    fetchMemories();
});