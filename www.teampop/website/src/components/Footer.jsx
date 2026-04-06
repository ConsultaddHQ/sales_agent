export default function Footer() {
  return (
    <footer className="w-full py-12 border-t border-[#222222] bg-[#131313]">
      <div className="flex flex-col md:flex-row justify-between items-center px-6 md:px-12 max-w-7xl mx-auto gap-4">
        <div className="text-lg font-black text-white">Hyperflex</div>
        <div className="text-[10px] font-medium tracking-widest uppercase text-neutral-500">
          &copy; {new Date().getFullYear()} Hyperflex
        </div>
      </div>
    </footer>
  )
}
