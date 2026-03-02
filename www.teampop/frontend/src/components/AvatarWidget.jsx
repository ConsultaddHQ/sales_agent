import React, { useState, useEffect, useRef, useCallback } from "react";
import { useConversation } from "@elevenlabs/react";
import "../styles/AvatarWidget.css";

const DUMMY_IMAGE = "/image.png";

// --- SHOPPING CARD (Style A) ---
const ShoppingCard = ({ product, isActive, highlightPrice, highlightDesc }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`shopping-card ${isActive ? "card-active" : "card-dimmed"}`}
    >
      <div className="shopping-card-info">
        <div className="shopping-card-title">{product.name}</div>
        {product.description && (
          <div className="flex flex-col gap-1">
            <div
              className={`shopping-card-desc text-sm text-gray-600 transition-all ${isActive && highlightDesc ? "desc-highlight" : ""} ${!isExpanded ? "line-clamp-2" : ""}`}
            >
              {product.description}
            </div>
            <button 
              onClick={(e) => { e.preventDefault(); setIsExpanded(!isExpanded); }}
              className="text-xs text-blue-400 self-start font-semibold mt-1"
            >
              {isExpanded ? "Show less" : "Read more"}
            </button>
          </div>
        )}
        <div
          className={`shopping-card-price text-xl font-bold mt-2 ${isActive && highlightPrice ? "price-glow text-green-400" : "text-green-300"}`}
        >
          {product.price || "Check Price"}
        </div>
        <a 
          href={product.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shopping-cta mt-3 text-center bg-white text-black px-6 py-2 rounded-full font-bold text-sm hover:bg-gray-200 transition"
        >
          Shop Now
        </a>
      </div>
    </div>
  );
};

// --- MARKDOWN FORMATTER ---
const formatMessage = (text) => {
  if (!text) return "";
  let formatted = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br />");
  formatted = formatted.replace(/(\d+\.)\s/g, "<br/>$1 ");
  return formatted;
};

// --- INNER COMPONENT ---
function AvatarInner({
  agentId,
  isOpen,
  setIsOpen,
  latestProducts,
  setLatestProducts,
  activeIndex,
  setActiveIndex,
  carouselRef,
  handleCarouselScroll,
  isProgrammaticScrollRef,
}) {
  const [agentSubtitle, setAgentSubtitle] = useState("");
  const [chatHistory, setChatHistory] = useState([]); // NEW: Chat history state
  const [isProductsHidden, setIsProductsHidden] = useState(false); // NEW: Hide/Show products state
  const [transientMessage, setTransientMessage] = useState(null);
  const [isFadingOut, setIsFadingOut] = useState(false);
  const [highlightPrice, setHighlightPrice] = useState(false);
  
  const transientTimeoutRef = useRef(null);
  const priceTimerRef = useRef(null);
  const subtitleTimerRef = useRef(null);
  const subtitleContainerRef = useRef(null);
  const chatScrollRef = useRef(null); // NEW: Chat auto-scroll reference
  const isSessionTransitioningRef = useRef(false);

  const showTransientMessage = useCallback(
    (text) => {
      if (isOpen) return;
      if (transientTimeoutRef.current) clearTimeout(transientTimeoutRef.current);

      setIsFadingOut(false);
      setTransientMessage(text);

      transientTimeoutRef.current = setTimeout(() => {
        setIsFadingOut(true);
        setTimeout(() => setTransientMessage(null), 300);
      }, 5000);
    },
    [isOpen],
  );

  const conversation = useConversation({
    onMessage: (message) => {
      const source = message?.source;
      const text =
        typeof message?.message === "string"
          ? message.message
          : typeof message?.text === "string"
            ? message.text
            : typeof message?.content === "string"
              ? message.content
              : "";

      if (text) {
        // Build the chat history safely (handles both unique and streaming chunks)
        setChatHistory((prev) => {
          const msgId = message?.id || message?.message_id;
          if (msgId) {
            const existingIdx = prev.findIndex((m) => m.id === msgId);
            if (existingIdx !== -1) {
              const updated = [...prev];
              updated[existingIdx] = { ...updated[existingIdx], text };
              return updated;
            }
            return [...prev, { id: msgId, source, text }];
          }
          // Fallback if no ID is present
          if (prev.length > 0 && prev[prev.length - 1].text === text) return prev;
          return [...prev, { id: Date.now(), source, text }];
        });
      }

      if (source === "ai") {
        setAgentSubtitle(text);
        if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
        subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 3000);

        const lower = text.toLowerCase();
        if (
          lower.includes("price") ||
          lower.includes("₹") ||
          lower.includes("rupees") ||
          lower.includes("cost")
        ) {
          if (priceTimerRef.current) clearTimeout(priceTimerRef.current);
          setHighlightPrice(true);
          priceTimerRef.current = setTimeout(
            () => setHighlightPrice(false),
            2500,
          );
        }
      }
    },
    onError: (error) => {
      console.error("ElevenLabs conversation error:", error);
    },
    clientTools: {
      update_products: async (parameters) => {
        console.log('Update tool called : ', parameters);
        
        const products = Array.isArray(parameters?.products)
          ? parameters.products
          : [];

        setLatestProducts(products);
        setIsProductsHidden(false); // Ensure overlay shows up when data updates
        setIsOpen(false); // Close chat to reveal shopping mode
        setActiveIndex(0);
        showTransientMessage(`Found ${products.length} products for you.`);
        return "UI updated successfully";
      },
    },
  });

  // Auto-scroll the subtitle text
  useEffect(() => {
    if (subtitleContainerRef.current) {
      subtitleContainerRef.current.scrollTop = subtitleContainerRef.current.scrollHeight;
    }
  }, [agentSubtitle]);

  // Auto-scroll the chat history
  useEffect(() => {
    if (chatScrollRef.current && isOpen) {
      chatScrollRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [chatHistory, isOpen]);

  let visualState = "IDLE";
  if (conversation.status === "connecting") {
    visualState = "CONNECTING";
  } else if (conversation.status === "connected") {
    visualState = conversation.isSpeaking ? "SPEAKING" : "LISTENING";
  }

  // Handle Programmatic Carousel Scrolling
  useEffect(() => {
    if (carouselRef.current && latestProducts.length > 0) {
      isProgrammaticScrollRef.current = true;
      const width = carouselRef.current.clientWidth;
      carouselRef.current.scrollTo({
        left: activeIndex * width,
        behavior: "smooth",
      });
      setTimeout(() => {
        isProgrammaticScrollRef.current = false;
      }, 600);
    }
  }, [activeIndex, latestProducts, carouselRef, isProgrammaticScrollRef]);

  useEffect(() => {
    return () => {
      if (transientTimeoutRef.current) clearTimeout(transientTimeoutRef.current);
      if (priceTimerRef.current) clearTimeout(priceTimerRef.current);
      if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    };
  }, []);

  const handleInteraction = async () => {
    if (isSessionTransitioningRef.current) return;

    try {
      isSessionTransitioningRef.current = true;
      if (conversation.status === "connected") {
        await conversation.endSession();
      } else if (
        conversation.status === "disconnected" ||
        conversation.status === "error"
      ) {
        if (!agentId || agentId === "YOUR_ELEVENLABS_AGENT_ID") {
          console.error("Missing ElevenLabs agentId. Set a valid agent ID.");
          return;
        }
        await conversation.startSession({
          agentId,
          connectionType: "webrtc",
        });
      }
    } catch (error) {
      console.error("Failed to start/stop conversation:", error);
      setAgentSubtitle("");
    } finally {
      isSessionTransitioningRef.current = false;
    }
  };

  // Check visibility logic
  const isShoppingMode = !isOpen && latestProducts.length > 0 && !isProductsHidden;

  return (
    <>
      {/* 1. SHOPPING MODE OVERLAY (Vertical Flex Layout) */}
      {isShoppingMode && (
        <div className="shopping-mode-overlay flex flex-col h-[100dvh] w-screen bg-black overflow-hidden relative z-40">
          
          {/* TOP: Header (Close Button) */}
          <div className="flex-none p-4 flex justify-end items-start absolute top-0 w-full z-50 pointer-events-none">
            {/* Close Button at top - Now minimizes the products instead of clearing them */}
            <button
              className="bg-black/40 hover:bg-black/60 backdrop-blur-md text-white rounded-full w-10 h-10 flex items-center justify-center text-xl shadow-lg transition-all pointer-events-auto"
              onClick={() => setIsProductsHidden(true)}
            >
              &times;
            </button>
          </div>

          {/* MID: Hero Stage (Active Product Image) */}
          <div className="flex-1 w-full relative min-h-0 bg-zinc-900">
            {latestProducts[activeIndex] && (
              <>
                <img
                  src={latestProducts[activeIndex].image_url || DUMMY_IMAGE}
                  alt={latestProducts[activeIndex].name}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.target.src = "https://placehold.co/400x400?text=Image+Unavailable";
                  }}
                />
                <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-black to-transparent pointer-events-none" />
              </>
            )}
          </div>

          {/* BOTTOM: The Interaction Zone */}
          <div className="flex-none w-full flex flex-col justify-end bg-black pb-4 px-4 z-10 pt-2 pointer-events-auto shrink-0">
            <div className="w-full mb-3">
              {latestProducts[activeIndex] && (
                <ShoppingCard 
                  product={latestProducts[activeIndex]} 
                  isActive={true} 
                  highlightPrice={highlightPrice} 
                />
              )}
            </div>

            <div 
              ref={subtitleContainerRef}
              className="w-full max-h-20 overflow-y-auto mb-3 no-scrollbar"
            >
              {agentSubtitle && (
                <div className="text-white/90 bg-black/40 p-2 rounded-lg text-sm backdrop-blur-sm border border-white/10 shadow-sm leading-snug">
                  {agentSubtitle}
                </div>
              )}
            </div>

            <div 
              className="w-full flex items-center overflow-x-auto hide-scrollbar gap-3 mb-4"
              ref={carouselRef}
              onScroll={handleCarouselScroll}
            >
              {latestProducts.map((p, idx) => (
                <div
                  key={idx}
                  className={`flex-shrink-0 transition-all duration-300 cursor-pointer rounded-xl overflow-hidden border-2 ${idx === activeIndex ? "border-blue-500 scale-100 opacity-100" : "border-transparent scale-90 opacity-60 hover:opacity-100"}`}
                  style={{ width: "60px", height: "60px" }}
                  onClick={() => setActiveIndex(idx)}
                >
                  <img
                    src={p.image_url || DUMMY_IMAGE}
                    alt={p.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.src = "https://placehold.co/400x400?text=Image+Unavailable";
                    }}
                  />
                </div>
              ))}
            </div>

            {/* Shopping Mode Orb Dock */}
            <div className="w-full flex items-center justify-center">
              <div
                className="orb-dock"
                style={{
                  position: "relative",
                  width: "100%",
                  margin: "0",
                  height: "50px",
                  boxShadow: "none",
                  background: "transparent",
                  border: "none",
                  padding: "0"
                }}
              >
                <div className={`dock-status flex-1 text-left text-xs uppercase font-bold tracking-wider ${visualState !== "IDLE" ? "text-green-400" : "text-gray-400"}`}>
                  {visualState === "IDLE" ? "Ready" : visualState}
                </div>

                <div className={`orb-wrapper flex-shrink-0 ${visualState} scale-75 cursor-pointer`} onClick={handleInteraction}>
                  <div className="orb-core"></div>
                </div>

                <div className="flex-1 flex justify-end">
                  <button className="dock-action text-xs text-gray-300 hover:text-white" onClick={() => setIsOpen(true)}>
                    View Chat
                  </button>
                </div>
              </div>
            </div>
            
          </div>
        </div>
      )}

      {/* 2. MAIN WIDGET CONTAINER (Normal non-shopping mode) */}
      <div className={`avatar-widget ${isOpen ? "mode-open" : "mode-closed"}`}>
        <div className="avatar-controls-column">
          
          {!isOpen && transientMessage && !isShoppingMode && (
            <div className={`transient-bubble ${isFadingOut ? "fading-out" : ""}`}>
              <span dangerouslySetInnerHTML={{ __html: formatMessage(transientMessage) }} />
            </div>
          )}

          {/* Floating Orb Dock */}
          {!isOpen && !isShoppingMode && (
            <div className="orb-dock">
              <div className={`dock-status ${visualState !== "IDLE" ? "active" : ""}`}>
                {visualState === "IDLE" ? "Ready" : visualState}
              </div>

              <div className={`orb-wrapper ${visualState}`} onClick={handleInteraction}>
                <div className="orb-core"></div>
              </div>

              <div className="flex-1 flex justify-end items-center gap-2 pr-1 z-50">
                {/* Shows a stylized "Products" toggle if they were minimized */}
                {latestProducts.length > 0 && isProductsHidden && (
                  <button 
                    className="text-xs font-bold text-blue-300 bg-blue-900/40 hover:bg-blue-800/60 px-3 py-1.5 rounded-md uppercase tracking-wider transition border border-blue-500/30 shadow-lg cursor-pointer"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsProductsHidden(false);
                      setIsOpen(false);
                    }}
                  >
                    Products
                  </button>
                )}
                <button className="dock-action text-gray-300 hover:text-white" onClick={() => setIsOpen(true)}>
                  Chat
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 3. FULL CHAT UI (Open State) */}
      {isOpen && (
        <div className="bubble flex flex-col h-[70vh] max-h-[600px] overflow-hidden">
          <div className="bubble-header flex-shrink-0 bg-zinc-900 border-b border-white/10">
            <span className="bubble-status font-semibold text-white">Live Session</span>
            <button className="expand-btn text-xl hover:text-white" onClick={() => setIsOpen(false)}>
              &times;
            </button>
          </div>
          
          <div className="bubble-content chat-history flex-1 overflow-y-auto flex flex-col gap-3 p-4 bg-zinc-900/50 scroll-smooth">
            {chatHistory.length === 0 ? (
              <div className="message-bubble assistant-message self-start bg-zinc-800 text-white p-3 rounded-xl rounded-tl-sm text-sm max-w-[85%] border border-white/5 shadow-sm">
                Hello! I'm your Team Pop AI agent. How can I help you today?
              </div>
            ) : (
              chatHistory.map((msg, idx) => (
                <div
                  key={idx}
                  className={`message-bubble p-3 text-sm max-w-[85%] shadow-md ${
                    msg.source === "user"
                      ? "user-message self-end bg-blue-600 text-white rounded-2xl rounded-tr-sm border border-blue-500"
                      : "assistant-message self-start bg-zinc-800 text-gray-100 rounded-2xl rounded-tl-sm border border-white/5"
                  }`}
                >
                  <span dangerouslySetInnerHTML={{ __html: formatMessage(msg.text) }} />
                </div>
              ))
            )}
            <div ref={chatScrollRef} className="h-1 flex-shrink-0" />
          </div>
        </div>
      )}
    </>
  );
}

export default function AvatarWidget({ agentId, preview = false }) {
  const resolvedAgentId =
    agentId || window.__TEAM_POP_AGENT_ID__ || "";
  const [isOpen, setIsOpen] = useState(preview);
  const [latestProducts, setLatestProducts] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const carouselRef = useRef(null);
  const isProgrammaticScrollRef = useRef(false);
  const scrollEndTimerRef = useRef(null);

  const handleCarouselScroll = useCallback(() => {
    if (isProgrammaticScrollRef.current) return; 
    if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
    scrollEndTimerRef.current = setTimeout(() => {
      if (carouselRef.current) {
        const scrollLeft = carouselRef.current.scrollLeft;
        const width = carouselRef.current.clientWidth;
        if (width > 0) {
          const newIndex = Math.round(scrollLeft / width);
          if (newIndex !== activeIndex) setActiveIndex(newIndex);
        }
      }
    }, 150); 
  }, [activeIndex]);

  if (!resolvedAgentId || resolvedAgentId === "YOUR_ELEVENLABS_AGENT_ID") {
    return <div className="avatar-widget-error">Missing ElevenLabs Agent ID</div>;
  }

  return (
    <AvatarInner
      agentId={resolvedAgentId}
      isOpen={isOpen}
      setIsOpen={setIsOpen}
      latestProducts={latestProducts}
      setLatestProducts={setLatestProducts}
      activeIndex={activeIndex}
      setActiveIndex={setActiveIndex}
      carouselRef={carouselRef}
      handleCarouselScroll={handleCarouselScroll}
      isProgrammaticScrollRef={isProgrammaticScrollRef}
    />
  );
}