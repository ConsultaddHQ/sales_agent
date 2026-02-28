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
        <div className="shopping-card-title">{product.title}</div>
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
          href={product.url}
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
  const [transientMessage, setTransientMessage] = useState(null);
  const [isFadingOut, setIsFadingOut] = useState(false);
  const [highlightPrice, setHighlightPrice] = useState(false);
  const transientTimeoutRef = useRef(null);
  const priceTimerRef = useRef(null);
  const subtitleTimerRef = useRef(null);
  const subtitleContainerRef = useRef(null);
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
      update_product: async (toolPayload) => {
        console.log('Update tool called : ',toolPayload)
        const products = Array.isArray(toolPayload?.parameters?.products)
          ? toolPayload.parameters.products
          : Array.isArray(toolPayload?.products)
            ? toolPayload.products
            : [];

        setLatestProducts(products);
        setIsOpen(true);
        setActiveIndex(0);
        showTransientMessage(`Found ${products.length} products for you.`);
        return "UI updated successfully";
      },
    },
  });

  useEffect(() => {
    if (subtitleContainerRef.current) {
      subtitleContainerRef.current.scrollTop = subtitleContainerRef.current.scrollHeight;
    }
  }, [agentSubtitle]);

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
      // Keep the guard up for the duration of the smooth scroll animation
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

  useEffect(() => {
    return () => {
      conversation.endSession().catch(() => {});
    };
  }, [conversation]);

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
        await navigator.mediaDevices.getUserMedia({ audio: true });
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

  const isShoppingMode = !isOpen && latestProducts.length > 0;

  return (
    <>
      {/* 1. SHOPPING MODE OVERLAY (Vertical Flex Layout) */}
      {isShoppingMode && (
        <div className="shopping-mode-overlay flex flex-col h-[100dvh] w-screen bg-black overflow-hidden relative">
          
          {/* TOP: Header (Close Button) */}
          <div className="flex-none p-4 flex justify-end items-start absolute top-0 w-full z-50 pointer-events-none">
            {/* Close Button at top */}
            <button
              className="bg-black/40 hover:bg-black/60 backdrop-blur-md text-white rounded-full w-10 h-10 flex items-center justify-center text-xl shadow-lg transition-all pointer-events-auto"
              onClick={() => setLatestProducts([])}
            >
              &times;
            </button>
          </div>

          {/* MID: Hero Stage (Active Product Image) */}
          <div className="flex-1 w-full relative min-h-0 bg-zinc-900">
            {latestProducts[activeIndex] && (
              <>
                <img
                  src={latestProducts[activeIndex].image || DUMMY_IMAGE}
                  alt={latestProducts[activeIndex].title}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.target.src = "https://placehold.co/400x400?text=Image+Unavailable";
                  }}
                />
                {/* Gradient for seamless blend into bottom section */}
                <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-black to-transparent pointer-events-none" />
              </>
            )}
          </div>

          {/* BOTTOM: The Interaction Zone */}
          <div className="flex-none w-full flex flex-col justify-end bg-black pb-4 px-4 z-10 pt-2 pointer-events-auto shrink-0">
            
            {/* 1. Product Details (Title, Desc, Price, Shop Now) */}
            <div className="w-full mb-3">
              {latestProducts[activeIndex] && (
                <ShoppingCard 
                  product={latestProducts[activeIndex]} 
                  isActive={true} 
                  highlightPrice={highlightPrice} 
                />
              )}
            </div>

            {/* 2. Teleprompter (Live AI Captions) */}
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

            {/* 3. Product Queue (Horizontal Thumbnails) */}
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
                    src={p.image || DUMMY_IMAGE}
                    alt={p.title}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.src = "https://placehold.co/400x400?text=Image+Unavailable";
                    }}
                  />
                </div>
              ))}
            </div>

            {/* 4. Command Deck (Orb) */}
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
                <div
                  className={`dock-status flex-1 text-left text-xs uppercase font-bold tracking-wider ${visualState !== "IDLE" ? "text-green-400" : "text-gray-400"}`}
                >
                  {visualState === "IDLE"
                    ? "Ready"
                    : visualState === "THINKING"
                      ? "Thinking"
                      : visualState === "SPEAKING"
                        ? "Speaking"
                        : visualState === "LISTENING"
                          ? "Listening"
                          : visualState === "CONNECTING"
                            ? "Connecting"
                            : visualState}
                </div>

                <div
                  className={`orb-wrapper flex-shrink-0 ${visualState} scale-75 cursor-pointer`}
                  onClick={handleInteraction}
                >
                  <div className="orb-core"></div>
                </div>

                <button
                  className="dock-action flex-1 text-right text-xs text-gray-300 hover:text-white"
                  onClick={() => setIsOpen(true)}
                >
                  View Chat
                </button>
              </div>
            </div>
            
          </div>
        </div>
      )}

      {/* 2. MAIN WIDGET CONTAINER (Normal non-shopping mode) */}
      <div className={`avatar-widget ${isOpen ? "mode-open" : "mode-closed"}`}>
        <div className="avatar-controls-column">
          {/* A. TRANSIENT MESSAGE (Floating Bubble) */}
          {!isOpen && transientMessage && !isShoppingMode && (
            <div
              className={`transient-bubble ${isFadingOut ? "fading-out" : ""}`}
            >
              <span
                dangerouslySetInnerHTML={{
                  __html: formatMessage(transientMessage),
                }}
              />
            </div>
          )}

          {/* B. THE FLOATING CAPSULE DOCK */}
          {!isOpen && !isShoppingMode && (
            <div className="orb-dock">
              {/* Left: Status */}
              <div
                className={`dock-status ${visualState !== "IDLE" ? "active" : ""}`}
              >
                {visualState === "IDLE"
                  ? "Ready"
                  : visualState === "THINKING"
                    ? "Thinking"
                    : visualState === "SPEAKING"
                      ? "Speaking"
                      : visualState === "LISTENING"
                        ? "Listening"
                        : visualState === "CONNECTING"
                          ? "Connecting"
                          : visualState}
              </div>

              {/* Center: Pop-out Orb */}
              <div
                className={`orb-wrapper ${visualState}`}
                onClick={handleInteraction}
              >
                <div className="orb-core">{/* Optional Visualizer */}</div>
              </div>

              {/* Right: View Chat */}
              <button className="dock-action" onClick={() => setIsOpen(true)}>
                View Chat
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3. FULL CHAT UI (Open State) - Reduced for now as chat history is not fully synced yet */}
      {isOpen && (
        <div className="bubble">
          <div className="bubble-header">
            <span className="bubble-status">Live Session</span>
            <button className="expand-btn" onClick={() => setIsOpen(false)}>
              &times;
            </button>
          </div>
          <div className="bubble-content chat-history">
            <div className="message-bubble assistant-message">
              Chat history is unavailable in this mode. Please use voice.
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function AvatarWidget({ agentId, preview = false }) {
  const resolvedAgentId =
    agentId || window.__TEAM_POP_AGENT_ID__ || "YOUR_ELEVENLABS_AGENT_ID";
  const [isOpen, setIsOpen] = useState(preview);
  const [latestProducts, setLatestProducts] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const carouselRef = useRef(null);
  const isProgrammaticScrollRef = useRef(false);
  const scrollEndTimerRef = useRef(null);

  // Debounced Scroll Handler — only responds to USER swipes, not programmatic scrolls
  const handleCarouselScroll = useCallback(() => {
    if (isProgrammaticScrollRef.current) return; // Guard: skip during programmatic scroll
    if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
    scrollEndTimerRef.current = setTimeout(() => {
      if (carouselRef.current) {
        const scrollLeft = carouselRef.current.scrollLeft;
        const width = carouselRef.current.clientWidth;
        // Make sure width is non-zero to avoid NaN
        if (width > 0) {
          const newIndex = Math.round(scrollLeft / width);
          if (newIndex !== activeIndex) setActiveIndex(newIndex);
        }
      }
    }, 150); // Wait 150ms after scroll stops to settle
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
