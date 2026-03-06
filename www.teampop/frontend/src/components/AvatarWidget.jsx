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
              className={`shopping-card-desc text-sm text-gray-600 transition-all ${!isExpanded ? "line-clamp-2" : ""}`}
            >
              {product.description}
            </div>
            <button
              onClick={(e) => {
                e.preventDefault();
                setIsExpanded(!isExpanded);
              }}
              className="text-xs text-blue-400 self-start font-semibold mt-1"
            >
              {isExpanded ? "Show less" : "Read more"}
            </button>
          </div>
        )}
        <div
          className={`shopping-card-price text-xl font-bold mt-2 ${isActive && highlightPrice ? "price-glow text-green-400" : "text-green-300"}`}
        >
          {product.price
            ? `₹${Number(product.price).toLocaleString("en-IN")}`
            : "Check Price"}
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
  activeView,
  setActiveView,
  latestProducts,
  setLatestProducts,
  activeIndex,
  setActiveIndex,
  carouselRef,
  handleCarouselScroll,
  isProgrammaticScrollRef,
}) {
  const [agentSubtitle, setAgentSubtitle] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [transientMessage, setTransientMessage] = useState(null);
  const [isFadingOut, setIsFadingOut] = useState(false);
  const [highlightPrice, setHighlightPrice] = useState(false);

  const transientTimeoutRef = useRef(null);
  const priceTimerRef = useRef(null);
  const subtitleTimerRef = useRef(null);
  const subtitleContainerRef = useRef(null);
  const chatContainerRef = useRef(null);
  const isSessionTransitioningRef = useRef(false);

  const showTransientMessage = useCallback(
    (text) => {
      if (activeView !== "NONE") return;
      if (transientTimeoutRef.current)
        clearTimeout(transientTimeoutRef.current);

      setIsFadingOut(false);
      setTransientMessage(text);

      transientTimeoutRef.current = setTimeout(() => {
        setIsFadingOut(true);
        setTimeout(() => setTransientMessage(null), 300);
      }, 5000);
    },
    [activeView],
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
          if (prev.length > 0 && prev[prev.length - 1].text === text)
            return prev;
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
    onError: (error) => console.error("ElevenLabs error:", error),
    clientTools: {
      update_products: async (parameters) => {
        console.log("Update tool called : ", parameters);
        const products = Array.isArray(parameters?.products)
          ? parameters.products
          : [];

        setLatestProducts(products);
        setActiveView("PRODUCTS");
        setActiveIndex(0);
        showTransientMessage(`Found ${products.length} products for you.`);
        return "UI updated successfully";
      },

      // New tool 1: Agent wants to pivot carousel during speech

      update_carousel_main_view: async (parameters) => {
        console.log("🔄 update_carousel_main_view called with:", parameters);

        let targetIndex = -1;

        // Prefer index if given (much more reliable)
        if (typeof parameters?.index === "number") {
          targetIndex = parameters.index;
        }
        // Fallback to id
        else if (parameters?.product_id) {
          targetIndex = latestProducts.findIndex(
            (p) => p.id === parameters.product_id,
          );
        }

        if (
          targetIndex >= 0 &&
          targetIndex < latestProducts.length &&
          targetIndex !== activeIndex
        ) {
          setActiveIndex(targetIndex);

          // Force scroll right now
          if (carouselRef.current) {
            const width = carouselRef.current.clientWidth;
            if (width > 0) {
              carouselRef.current.scrollTo({
                left: targetIndex * width,
                behavior: "smooth",
              });
            }
          }

          const usedId = latestProducts[targetIndex]?.id || "unknown";
          return `Carousel moved to index ${targetIndex} (product_id: ${usedId})`;
        }

        return "Could not move carousel (invalid index or id)";
      },

      // New tool 2: Enrich main view + optional short TTS (called by agent OR manually by us)
      // New tool 2: Enrich main view + short narration (NO crashing speak)
      product_desc_of_main_view: async (parameters) => {
        console.log("🗣️ product_desc_of_main_view called with:", parameters);

        const desc = parameters?.product_desc;
        if (!desc?.product_id) return "Missing product_desc";

        // speak() was crashing the entire tool chain — removed for now
        console.log(
          `[Narration would be]: Ooh, ${desc.name} — ₹${Number(desc.price).toLocaleString("en-IN")}, ${desc.description.split(/[.!?]\s/)[0] || ""}…`,
        );

        return `Main view enriched for ${desc.product_id}`;
      },
    },
  });

  // Helper for proactive narration on manual scroll or thumbnail click

  const syncMainProduct = useCallback(
    (product) => {
      if (!product?.id || !conversation.isActive) return;

      conversation.clientTools?.product_desc_of_main_view?.({
        product_desc: {
          product_id: product.id,
          name: product.name || "",
          description: product.description || "",
          price: product.price || 0,
        },
      });
    },
    [conversation],
  );

  useEffect(() => {
    if (subtitleContainerRef.current) {
      subtitleContainerRef.current.scrollTop =
        subtitleContainerRef.current.scrollHeight;
    }
  }, [agentSubtitle]);

  useEffect(() => {
    if (chatContainerRef.current && activeView === "CHAT") {
      const container = chatContainerRef.current;
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distanceFromBottom < 150 || chatHistory.length <= 1) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [chatHistory, activeView]);

  let visualState = "IDLE";
  if (conversation.status === "connecting") visualState = "CONNECTING";
  else if (conversation.status === "connected")
    visualState = conversation.isSpeaking ? "SPEAKING" : "LISTENING";

  useEffect(() => {
    if (carouselRef.current && latestProducts.length > 0) {
      isProgrammaticScrollRef.current = true;
      const width = carouselRef.current.clientWidth;
      carouselRef.current.scrollTo({
        left: activeIndex * width,
        behavior: "smooth",
      });
      syncMainProduct(latestProducts[activeIndex]);
      setTimeout(() => {
        isProgrammaticScrollRef.current = false;
      }, 600);
    }
  }, [
    activeIndex,
    latestProducts,
    carouselRef,
    isProgrammaticScrollRef,
    syncMainProduct,
  ]);

  // Trigger narration + index update on manual/user scroll end
  // Programmatic slide + narration when activeIndex changes (agent or click)
  // Manual/user scroll → narration
  useEffect(() => {
    const container = carouselRef.current;
    if (!container) return;

    let timeoutId;

    const handleScroll = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        if (isProgrammaticScrollRef.current) return;

        const scrollLeft = container.scrollLeft;
        const width = container.clientWidth;
        if (width <= 0) return;

        const newIndex = Math.round(scrollLeft / width);
        if (newIndex !== activeIndex && latestProducts[newIndex]) {
          console.log("Manual scroll → new index", newIndex);
          setActiveIndex(newIndex);
          syncMainProduct(latestProducts[newIndex]);
        }
      }, 150);
    };

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      clearTimeout(timeoutId);
    };
  }, [latestProducts, activeIndex, syncMainProduct, isProgrammaticScrollRef]);

  useEffect(() => {
    return () => {
      if (transientTimeoutRef.current)
        clearTimeout(transientTimeoutRef.current);
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
        await conversation.startSession({ agentId, connectionType: "webrtc" });
      }
    } catch (error) {
      console.error("Failed interaction:", error);
      setAgentSubtitle("");
    } finally {
      isSessionTransitioningRef.current = false;
    }
  };

  return (
    <>
      {/* 1. SHOPPING / PRODUCTS MODE OVERLAY */}
      {activeView === "PRODUCTS" && (
        <div className="shopping-mode-overlay flex flex-col h-[100dvh] w-screen bg-black overflow-hidden relative z-40">
          {/* TOP Header */}
          <div className="flex-none p-4 flex justify-end items-start absolute top-0 w-full z-50 pointer-events-none">
            <button
              className="bg-black/40 hover:bg-black/60 backdrop-blur-md text-white rounded-full w-10 h-10 flex items-center justify-center text-xl shadow-lg transition-all pointer-events-auto"
              onClick={() => setActiveView("NONE")}
            >
              &times;
            </button>
          </div>

          {latestProducts.length > 0 ? (
            <>
              {/* MID: Hero Stage */}
              <div className="flex-1 w-full relative min-h-0 bg-zinc-900">
                {latestProducts[activeIndex] && (
                  <>
                    <img
                      src={latestProducts[activeIndex].image_url || DUMMY_IMAGE}
                      alt={latestProducts[activeIndex].name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.target.src =
                          "https://placehold.co/400x400?text=Image+Unavailable";
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
                      onClick={() => {
                        console.log("👆 Thumbnail clicked → index", idx);
                        setActiveIndex(idx); // ← useEffect will trigger slide + narration
                      }}
                    >
                      <img
                        src={p.image_url || DUMMY_IMAGE}
                        alt={p.name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.target.src =
                            "https://placehold.co/400x400?text=Image+Unavailable";
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            // EMPTY STATE
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-zinc-900 pointer-events-auto pt-16">
              <div className="w-20 h-20 bg-zinc-800 rounded-full flex items-center justify-center mb-6 border border-zinc-700 shadow-xl">
                <svg
                  className="w-10 h-10 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
                  ></path>
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-white mb-3 tracking-wide">
                No Products Yet
              </h2>
              <p className="text-gray-400 text-sm max-w-[250px] mx-auto leading-relaxed">
                Tap the orb below and ask me to find something for you!
              </p>
            </div>
          )}

          {/* DOCK FOR SHOPPING MODE */}
          <div className="flex-none w-full bg-black pb-6 px-4 z-10 pointer-events-auto">
            <div className="w-full flex items-center justify-center mt-2">
              <div
                className="orb-dock px-2 min-w-[280px]"
                style={{
                  position: "relative",
                  width: "100%",
                  margin: "0",
                  height: "50px",
                  boxShadow: "none",
                  background: "transparent",
                  border: "none",
                  padding: "0",
                }}
              >
                <div className="flex-1 flex justify-start items-center">
                  <button className="dock-action text-[11px] font-bold text-gray-500 uppercase tracking-wider cursor-default">
                    Products
                  </button>
                </div>

                <div className="relative flex-shrink-0 flex flex-col items-center justify-center">
                  {/* Status pill ABOVE the orb */}
                  <span
                    className={`absolute -top-7 text-[9px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full whitespace-nowrap transition-colors ${visualState !== "IDLE" ? "bg-green-500/20 text-green-400 border border-green-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]" : "bg-zinc-800/80 text-gray-400 border border-white/5"}`}
                  >
                    {visualState === "IDLE" ? "Ready" : visualState}
                  </span>

                  <div
                    className={`orb-wrapper flex-shrink-0 ${visualState} scale-75 cursor-pointer mt-1`}
                    onClick={handleInteraction}
                  >
                    <div className="orb-core"></div>
                  </div>
                </div>

                <div className="flex-1 flex justify-end items-center">
                  <button
                    className="dock-action text-[11px] font-bold text-gray-300 hover:text-white uppercase tracking-wider"
                    onClick={() => setActiveView("CHAT")}
                  >
                    Chat
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. MAIN WIDGET CONTAINER (Normal Home Dock) */}
      {activeView === "NONE" && (
        <div className="avatar-widget mode-closed">
          <div className="avatar-controls-column">
            {transientMessage && (
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

            {/* SYMMETRICAL HOME DOCK */}
            <div className="orb-dock px-4 min-w-[280px] shadow-2xl border border-white/10 mt-6">
              <div className="flex-1 flex justify-start items-center">
                <button
                  className="dock-action font-bold uppercase tracking-wider text-[11px] text-gray-300 hover:text-white transition-colors"
                  onClick={() => setActiveView("PRODUCTS")}
                >
                  Products
                </button>
              </div>

              <div className="relative flex-shrink-0 flex flex-col items-center justify-center">
                {/* Status pill ABOVE the orb */}
                <span
                  className={`absolute -top-8 text-[9px] uppercase font-bold tracking-widest px-2.5 py-1 rounded-full whitespace-nowrap transition-all duration-300 ${visualState !== "IDLE" ? "bg-green-500/20 text-green-400 border border-green-500/30 shadow-[0_0_15px_rgba(34,197,94,0.3)]" : "bg-zinc-800/80 text-gray-400 border border-white/5"}`}
                >
                  {visualState === "IDLE" ? "Tap to speak" : visualState}
                </span>

                <div
                  className={`orb-wrapper ${visualState} cursor-pointer`}
                  onClick={handleInteraction}
                >
                  <div className="orb-core"></div>
                </div>
              </div>

              <div className="flex-1 flex justify-end items-center">
                <button
                  className="dock-action font-bold uppercase tracking-wider text-[11px] text-gray-300 hover:text-white transition-colors"
                  onClick={() => setActiveView("CHAT")}
                >
                  Chat
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. FULL CHAT UI */}
      {activeView === "CHAT" && (
        <div className="avatar-widget mode-open">
          <div className="bubble flex flex-col h-[70vh] max-h-[600px] overflow-hidden shadow-2xl border border-white/10 relative pointer-events-auto">
            {/* Header with strictly enforced Close Button */}
            <div className="bubble-header flex-shrink-0 bg-zinc-900 border-b border-white/10 px-4 py-3 flex justify-between items-center z-50">
              <span className="font-semibold text-white tracking-wide text-sm flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${visualState !== "IDLE" ? "bg-green-500 animate-pulse" : "bg-gray-500"}`}
                />
                Live Session
              </span>

              {/* Overriding previous generic CSS to guarantee clickability */}
              <button
                className="text-gray-400 hover:text-white transition-colors cursor-pointer p-1 -mr-1 rounded-md hover:bg-white/10 z-50 pointer-events-auto"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setActiveView("NONE");
                }}
                aria-label="Close Chat"
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M6 18L18 6M6 6l12 12"
                  ></path>
                </svg>
              </button>
            </div>

            <div
              className="bubble-content chat-history flex-1 overflow-y-auto flex flex-col gap-3 p-4 bg-zinc-900/95"
              ref={chatContainerRef}
            >
              {chatHistory.length === 0 ? (
                <div className="message-bubble assistant-message self-start bg-zinc-800 text-gray-200 p-3 rounded-xl rounded-tl-sm text-sm max-w-[85%] border border-white/5 shadow-sm">
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
                    <span
                      dangerouslySetInnerHTML={{
                        __html: formatMessage(msg.text),
                      }}
                    />
                  </div>
                ))
              )}
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
  const [activeView, setActiveView] = useState(preview ? "CHAT" : "NONE");
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
    return (
      <div className="avatar-widget-error">Missing ElevenLabs Agent ID</div>
    );
  }

  return (
    <AvatarInner
      agentId={resolvedAgentId}
      activeView={activeView}
      setActiveView={setActiveView}
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
