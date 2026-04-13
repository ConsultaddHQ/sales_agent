import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  useConversation,
  useConversationClientTool,
} from "@elevenlabs/react";
import "../styles/AvatarWidget.css";

const DUMMY_IMAGE = "/image.png";
const WIDGET_LAYER_STYLE = {
  position: "fixed",
  bottom: "0",
  left: "0",
  width: "100%",
  height: "100%",
  zIndex: 2147483647,
  pointerEvents: "none",
  isolation: "isolate",
};

const ShoppingCard = ({ product, isActive, highlightPrice }) => {
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

const formatMessage = (text) => {
  if (!text) return "";
  let formatted = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br />");
  formatted = formatted.replace(/(\d+\.)\s/g, "<br/>$1 ");
  return formatted;
};

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
}) {
  const [agentSubtitle, setAgentSubtitle] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [highlightPrice, setHighlightPrice] = useState(false);

  const priceTimerRef = useRef(null);
  const subtitleTimerRef = useRef(null);
  const chatContainerRef = useRef(null);
  const isSessionTransitioningRef = useRef(false);
  const latestProductsRef = useRef([]);
  // Tracks whether the current activeIndex change came from the agent tool
  const isAgentTriggeredRef = useRef(false);
  const isSyntheticMessageRef = useRef(false);
  const syncDebounceRef = useRef(null);

  useEffect(() => {
    return () => {
      clearTimeout(priceTimerRef.current);
      clearTimeout(subtitleTimerRef.current);
      clearTimeout(syncDebounceRef.current);
    };
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop =
        chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  useEffect(() => {
    latestProductsRef.current = latestProducts;
  }, [latestProducts]);

  const safeIndex = Math.min(
    activeIndex,
    Math.max(0, latestProducts.length - 1),
  );

  const latencyRef = useRef({ userSpeechAt: null, firstAiAt: null, productsAt: null, cycle: 0 });

  function _startLatencyTimer(userText) {
    const now = performance.now();
    latencyRef.current = { userSpeechAt: now, firstAiAt: null, productsAt: null, cycle: latencyRef.current.cycle + 1 };
    console.log(`%c⏱ [Cycle ${latencyRef.current.cycle}] User spoke: "${userText.slice(0, 50)}"`, "color: #4fc3f7; font-weight: bold");
  }

  function _markFirstAi() {
    const lc = latencyRef.current;
    if (lc.userSpeechAt && !lc.firstAiAt) {
      lc.firstAiAt = performance.now();
      const ms = Math.round(lc.firstAiAt - lc.userSpeechAt);
      console.log(`%c⏱ [Cycle ${lc.cycle}] First AI response: ${ms}ms`, "color: #81c784; font-weight: bold");
    }
  }

  function _markProductsArrived(count) {
    const lc = latencyRef.current;
    if (lc.userSpeechAt) {
      lc.productsAt = performance.now();
      const totalMs = Math.round(lc.productsAt - lc.userSpeechAt);
      const fromAi = lc.firstAiAt ? Math.round(lc.productsAt - lc.firstAiAt) : "N/A";
      console.log(
        `%c⏱ [Cycle ${lc.cycle}] Products in carousel (${count} items): ${totalMs}ms total | ${fromAi}ms after first AI`,
        "color: #ffb74d; font-weight: bold; font-size: 13px"
      );
      console.log(
        `%c⏱ [Cycle ${lc.cycle}] BREAKDOWN → User→AI: ${lc.firstAiAt ? Math.round(lc.firstAiAt - lc.userSpeechAt) : "?"}ms | User→Products: ${totalMs}ms`,
        "color: #ce93d8; font-weight: bold; font-size: 14px"
      );
    }
  }

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

      if (source === "user" && isSyntheticMessageRef.current) {
        isSyntheticMessageRef.current = false;
        return;
      }

      // Start latency timer when user speaks
      if (source === "user" && text) {
        _startLatencyTimer(text);
      }

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
        _markFirstAi();
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
    onDisconnect: (details) => {
      console.error(
        "[ElevenLabs] Disconnected:",
        "reason=", details?.reason,
        "closeCode=", details?.closeCode,
        "closeReason=", details?.closeReason,
        "message=", details?.message,
        "context=", details?.context,
      );
    },
  });

  useConversationClientTool("update_products", (parameters) => {
    console.log("Update tool called : ", parameters);
    const products = Array.isArray(parameters?.products)
      ? parameters.products
      : [];

    _markProductsArrived(products.length);

    setLatestProducts(products);
    latestProductsRef.current = products;
    setActiveView("PRODUCTS");
    setActiveIndex(0);
    setAgentSubtitle(`Found ${products.length} products for you`);
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 3000);
    return "UI updated successfully";
  });

  useConversationClientTool("update_carousel_main_view", (parameters) => {
    console.log("update_carousel_main_view called with:", parameters);

    const products = latestProductsRef.current;
    let targetIndex = -1;
    if (typeof parameters?.index === "number") {
      targetIndex = parameters.index;
    } else if (parameters?.product_id) {
      targetIndex = products.findIndex(
        (p) => p.id === parameters.product_id,
      );
    }

    if (targetIndex < 0 || targetIndex >= products.length) {
      return `Invalid index ${targetIndex}. Products available: 0-${products.length - 1}.`;
    }
    isAgentTriggeredRef.current = true;
    setActiveIndex(targetIndex);
    console.log(
      `[Agent] Carousel -> index ${targetIndex} (${products[targetIndex]?.name})`,
    );
    return `Carousel moved to index ${targetIndex}: ${products[targetIndex]?.name}`;
  });

  useConversationClientTool("product_desc_of_main_view", (parameters) => {
    console.log("product_desc_of_main_view called with:", parameters);
    const desc = parameters?.product_desc;
    if (!desc?.product_id) return "Missing product_desc";
    const label = `${desc.name || ""} - $${Number(desc.price || 0).toLocaleString("en-US")}`;
    setAgentSubtitle(label);
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 5000);
    setHighlightPrice(true);
    if (priceTimerRef.current) clearTimeout(priceTimerRef.current);
    priceTimerRef.current = setTimeout(
      () => setHighlightPrice(false),
      2500,
    );
    console.log(`[product_desc] UI updated for: ${desc.name}`);
    return `Main view enriched for ${desc.product_id}`;
  });

  const { sendContextualUpdate, sendUserMessage } = conversation;

  const visualState =
    conversation.status === "connected"
      ? "ACTIVE"
      : conversation.status === "error"
        ? "ERROR"
        : "IDLE";

  const syncMainProduct = useCallback(
    (product) => {
      if (!product?.id) return;
      if (conversation.status !== "connected") {
        setAgentSubtitle(
          `${product.name} — ₹${Number(product.price).toLocaleString("en-IN")}`,
        );
        if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
        subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 4000);
        return;
      }

      if (syncDebounceRef.current) clearTimeout(syncDebounceRef.current);
      syncDebounceRef.current = setTimeout(() => {
        console.log("[sync] Sending product context to agent:", product.name);

        sendContextualUpdate(
          `[CAROUSEL UPDATE] The user just manually selected a new product on screen. ` +
          `Product name: "${product.name}". ` +
          `Price: ₹${Number(product.price).toLocaleString("en-IN")}. ` +
          `Please talk about this product naturally in your next response.`,
        );

        isSyntheticMessageRef.current = true;
        sendUserMessage("Tell me about this one");
      }, 600);
    },
    [conversation.status, sendContextualUpdate, sendUserMessage],
  );

  useEffect(() => {
    const carouselEl = carouselRef.current;
    if (!carouselEl || !latestProducts[safeIndex]) return;
    console.log(
      `[Index Changed] safeIndex = ${safeIndex}, agentTriggered = ${isAgentTriggeredRef.current}`,
    );
    const thumbnailEl = carouselEl.children[safeIndex];
    if (thumbnailEl) {
      thumbnailEl.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      });
      console.log(`[Scroll OK] Thumbnail ${safeIndex} scrolled into view`);
    }
    isAgentTriggeredRef.current = false;
  }, [latestProducts, safeIndex]);

  const handleInteraction = () => {
    if (isSessionTransitioningRef.current) return;
    if (conversation.status === "connecting") return;
    isSessionTransitioningRef.current = true;
    if (conversation.status === "connected") {
      conversation.endSession();
    } else if (
      conversation.status === "disconnected" ||
      conversation.status === "error"
    ) {
      conversation.startSession({ agentId, connectionType: "websocket" });
    }
    setTimeout(() => {
      isSessionTransitioningRef.current = false;
    }, 500);
  };

  return (
    <>
      {activeView === "PRODUCTS" && (
        <div className="shopping-mode-overlay flex flex-col h-[100dvh] w-screen bg-black overflow-hidden relative z-40">
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
              <div className="flex-1 w-full relative min-h-0 bg-zinc-900">
                {latestProducts[safeIndex] && (
                  <>
                    <img
                      src={latestProducts[safeIndex].local_image_url || latestProducts[safeIndex].image_url || DUMMY_IMAGE}
                      alt={latestProducts[safeIndex].name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        const currentProduct = latestProducts[safeIndex];
                        if (currentProduct && e.target.src !== currentProduct.image_url && currentProduct.image_url) {
                          e.target.src = currentProduct.image_url;
                        } else {
                          e.target.src = 'https://placehold.co/400x400?text=No+Image';
                        }
                      }}
                    />
                    <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-black to-transparent pointer-events-none" />
                  </>
                )}
              </div>

              <div className="flex-none w-full flex flex-col justify-end bg-black pb-4 px-4 z-10 pt-2 pointer-events-auto shrink-0">
                <div className="w-full mb-3">
                  {latestProducts[safeIndex] && (
                    <ShoppingCard
                      product={latestProducts[safeIndex]}
                      isActive={true}
                      highlightPrice={highlightPrice}
                    />
                  )}
                </div>

                <div
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
                      key={p.id || idx}
                      className={`flex-shrink-0 transition-all duration-300 cursor-pointer rounded-xl overflow-hidden border-2 ${idx === safeIndex ? "border-blue-500 scale-100 opacity-100" : "border-transparent scale-90 opacity-60 hover:opacity-100"}`}
                      style={{ width: "60px", height: "60px" }}
                      onClick={() => {
                        console.log(
                          `[Thumbnail] Click → index ${idx} (${latestProducts[idx]?.name || "unknown"})`,
                        );
                        isAgentTriggeredRef.current = false;
                        setActiveIndex(idx);
                        syncMainProduct(latestProducts[idx]);
                      }}
                    >
                      <img
                        src={p.local_image_url || p.image_url || DUMMY_IMAGE}
                        alt={p.name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          if (p && e.target.src !== p.image_url && p.image_url) {
                            e.target.src = p.image_url;
                          } else {
                            e.target.src = 'https://placehold.co/400x400?text=No+Image';
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
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

      {activeView === "NONE" && (
        <div className="avatar-widget mode-closed">
          <div className="avatar-controls-column">
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

      {activeView === "CHAT" && (
        <div className="avatar-widget mode-open">
          <div className="bubble flex flex-col h-[70vh] max-h-[600px] overflow-hidden shadow-2xl border border-white/10 relative pointer-events-auto">
            <div className="bubble-header flex-shrink-0 bg-zinc-900 border-b border-white/10 px-4 py-3 flex justify-between items-center z-50">
              <span className="font-semibold text-white tracking-wide text-sm flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${visualState !== "IDLE" ? "bg-green-500 animate-pulse" : "bg-gray-500"}`}
                />
                Live Session
              </span>

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
                chatHistory.map((msg) => (
                  <div
                    key={msg.id}
                    className={`message-bubble p-3 text-sm max-w-[85%] shadow-md ${msg.source === "user"
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

function AvatarWidget({ agentId, preview = false }) {
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
      if (!carouselRef.current) return;
      const container = carouselRef.current;
      const children = Array.from(container.children);
      if (!children.length) return;
      const containerCenter =
        container.getBoundingClientRect().left + container.clientWidth / 2;
      let closest = 0;
      let minDist = Infinity;
      children.forEach((child, i) => {
        const rect = child.getBoundingClientRect();
        const childCenter = rect.left + rect.width / 2;
        const dist = Math.abs(childCenter - containerCenter);
        if (dist < minDist) {
          minDist = dist;
          closest = i;
        }
      });
      if (closest !== activeIndex) setActiveIndex(closest);
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
    />
  );
}

export default function LayeredAvatarWidget(props) {
  return (
    <div style={WIDGET_LAYER_STYLE}>
      <AvatarWidget {...props} />
    </div>
  );
}
