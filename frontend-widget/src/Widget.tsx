import { useConversation } from "@elevenlabs/react";
import { useState, useEffect } from "react";
import { Mic, Pause, Play, X } from "lucide-react";
import { motion } from "framer-motion";

type Product = {
  id: string;
  name: string;
  price: number;
  image_url: string;
  description: string;
};

function Widget() {
  const storeId = window.__HYPERFLEX_WIDGET_STORE_ID__ || "aa538422-17d1-4b2c-8d02-d512405d929b";
  const position: "bottom-left" | "bottom-right" = window.__HYPERFLEX_WIDGET_POSITION__ || "bottom-right";
  const agentId = window.__HYPERFLEX_WIDGET_AGENT_ID__ || "";

  const [transcription, setTranscription] = useState("");
  const [isPaused, setIsPaused] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conversation = useConversation({
    micMuted: isPaused,
    clientTools: {
      update_products: (params: { products: Product[] }) => {
        console.log("update_products called with:", params);
        const productsArray = params?.products ?? [];
        console.log("Parsed products:", productsArray);
        setProducts(
          productsArray.filter((p: Product) => p && p.id && p.name && typeof p.price === "number")
        );
      },
      highlight_product: (params: { product_id: string }) => {
        const el = document.getElementById(`product-${params.product_id}`);
        if (el) {
          el.classList.add("ring-4", "ring-green-400", "scale-105");
          setTimeout(() => el.classList.remove("ring-4", "ring-green-400", "scale-105"), 4000);
        }
      },
      focus_product: (params: { product_id: string }) => {
        document.getElementById(`product-${params.product_id}`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      },
    },
    onMessage: (msg) => {
      if (msg.source === "user" || msg.source === "ai") {
        setTranscription(msg.message ?? "");
      }
    },
    onError: (message, context) => {
      console.error("Conversation error:", message, context);
      setError(message);
    },
  });

  const { status } = conversation;

  useEffect(() => {
    if (isOpen && status === "disconnected" && agentId) {
      const start = async () => {
        try {
          await conversation.startSession({
            agentId,
            connectionType: "webrtc",
            dynamicVariables: {
              store_id: storeId,           // ← very useful for your search_products tool
            },
          });
          setError(null);
        } catch (err: unknown) {
          console.error("startSession failed:", err);
          setError((err as Error).message || "Connection failed. Check agent ID and network.");
        }
      };
      start();
    }

    return () => {
      if (status === "connected") {
        conversation.endSession().catch(console.error);
      }
    };
  }, [isOpen, status, agentId, storeId, conversation]);

  const justify = position === "bottom-right" ? "justify-end" : "justify-start";

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`fixed bottom-6 ${position === "bottom-left" ? "left-6" : "right-6"} w-14 h-14 bg-gradient-to-br from-purple-600 to-pink-600 rounded-full shadow-xl flex items-center justify-center z-50 transition-all hover:scale-110 hover:shadow-2xl focus:outline-none focus:ring-4 focus:ring-purple-300/50`}
      >
        <Mic className="w-7 h-7 text-white" />
      </button>

      {isOpen && (
        <div className={`fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end ${justify} p-4`}>
          <motion.div
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-white rounded-t-3xl w-full max-w-md h-[85vh] max-h-[580px] flex flex-col overflow-hidden shadow-2xl border border-gray-100"
          >
            {/* Header */}
            <div className="bg-gradient-to-r from-purple-600 to-pink-600 p-5 text-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 bg-white/25 rounded-full flex items-center justify-center ring-2 ring-white/30">
                  <Mic className="w-6 h-6" />
                </div>
                <div>
                  <p className="font-bold text-lg">Shop Assistant</p>
                  <p className="text-xs opacity-90 mt-0.5">
                    {error ? `Error: ${error}` : status === "connected" ? "Connected • Listening" : "Connecting..."}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 hover:bg-white/20 rounded-full transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Transcription */}
            <div className="p-4 bg-gradient-to-b from-gray-50 to-white text-gray-800 text-sm border-b border-gray-200 min-h-[4rem] max-h-28 overflow-y-auto">
              {transcription || (status === "connected" ? "I'm listening... say something!" : "Tap mic to start")}
            </div>

            {/* Products - modern card style */}
            <div className="flex-1 overflow-y-auto p-4 bg-gradient-to-b from-white to-gray-50">
              {products.length > 0 ? (
                <div className="space-y-4 pb-4">
                  {products.map((p) => (
                    <motion.div
                      key={p.id}
                      id={`product-${p.id}`}
                      className="bg-white rounded-xl shadow-md overflow-hidden hover:shadow-xl transition-all duration-300 border border-gray-100"
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4 }}
                    >
                      <div className="flex">
                        <img
                          src={p.image_url}
                          alt={p.name}
                          className="w-24 h-24 object-cover"
                        />
                        <div className="p-3 flex-1">
                          <h3 className="font-semibold text-base text-gray-900 line-clamp-2">{p.name}</h3>
                          <p className="text-green-600 font-bold text-lg mt-1">${p.price.toFixed(2)}</p>
                          <p className="text-sm text-gray-600 mt-1.5 line-clamp-2">{p.description}</p>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center px-6 text-gray-500">
                  <Mic className="w-12 h-12 text-purple-400 mb-4 opacity-70" />
                  <p className="font-medium text-lg">No products yet</p>
                  <p className="mt-2">Ask me about anything — shirts, pants, colors, prices...</p>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="p-4 bg-white border-t border-gray-200 flex justify-center">
              <button
                onClick={() => setIsPaused(!isPaused)}
                disabled={status !== "connected"}
                className={`w-40 h-12 rounded-full font-medium text-white flex items-center justify-center gap-2 shadow-lg transition-all ${
                  isPaused
                    ? "bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700"
                    : "bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700"
                } disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none`}
              >
                {isPaused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
                {isPaused ? "Resume" : "Pause"}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </>
  );
}

export default Widget;