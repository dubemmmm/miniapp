(() => {
    const STORAGE_KEY = 'cw-chat-id';
    const CHAT_ENDPOINT = '/api/chat/';

    const getCookie = (name) => {
        const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return match ? decodeURIComponent(match.pop()) : '';
    };

    const getChatId = () => {
        try {
            const cached = localStorage.getItem(STORAGE_KEY);
            if (cached) return cached;
            const id = crypto.randomUUID ? crypto.randomUUID() : `chat-${Date.now()}`;
            localStorage.setItem(STORAGE_KEY, id);
            return id;
        } catch (_) {
            return `chat-${Date.now()}`;
        }
    };

    const scrollChatToBottom = () => {
        const chatBody = document.getElementById('chat-widget-body');
        if (chatBody) {
            chatBody.scrollTop = chatBody.scrollHeight;
        }
    };

    const closeChatWidget = () => {
        const container = document.getElementById('chat-widget-container');
        const button = document.getElementById('chat-widget-button');
        if (container) container.style.display = 'none';
        if (button) button.style.display = 'flex';
    };

    const createTypingIndicator = () => {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message bot';
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
        wrapper.appendChild(indicator);
        return wrapper;
    };

    const sendChatMessage = async () => {
        const chatInput = document.getElementById('chat-widget-input');
        const chatBody = document.getElementById('chat-widget-body');
        if (!chatInput || !chatBody) return;

        const message = chatInput.value.trim();
        if (!message) return;

        const userBubble = document.createElement('div');
        userBubble.className = 'chat-message user';
        userBubble.textContent = message;
        chatBody.appendChild(userBubble);
        scrollChatToBottom();

        chatInput.value = '';

        const typingIndicator = createTypingIndicator();
        chatBody.appendChild(typingIndicator);
        scrollChatToBottom();

        try {
            const response = await fetch(CHAT_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    chatId: getChatId(),
                    message,
                    route: window.ChatWidgetConfig?.webhook?.route || 'general'
                })
            });

            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = {};
            }

            typingIndicator.remove();
            const botBubble = document.createElement('div');
            botBubble.className = 'chat-message bot';
            botBubble.innerHTML = data.output || data.reply || 'Thanks! A member of our team will get back to you shortly.';
            chatBody.appendChild(botBubble);
            scrollChatToBottom();
        } catch (error) {
            console.error('Chat widget error:', error);
            typingIndicator.remove();
            const errorBubble = document.createElement('div');
            errorBubble.className = 'chat-message bot';
            errorBubble.textContent = 'Sorry, something went wrong. Please try again.';
            chatBody.appendChild(errorBubble);
            scrollChatToBottom();
        }
    };

    const initChatWidget = () => {
        const chatButton = document.getElementById('chat-widget-button');
        const chatContainer = document.getElementById('chat-widget-container');
        if (!chatButton || !chatContainer) return;

        closeChatWidget();

        chatButton.addEventListener('click', () => {
            chatContainer.style.display = 'flex';
            chatButton.style.display = 'none';
            scrollChatToBottom();
        });

        const sendButton = document.getElementById('chat-widget-send');
        if (sendButton) {
            sendButton.addEventListener('click', sendChatMessage);
        }

        const chatInput = document.getElementById('chat-widget-input');
        if (chatInput) {
            chatInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    sendChatMessage();
                }
            });
        }
    };

    document.addEventListener('DOMContentLoaded', initChatWidget);
    window.closeChatWidget = closeChatWidget;
})();
