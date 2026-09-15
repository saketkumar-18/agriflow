// Generates simple solid-color PNG app icons (no deps, raw PNG + zlib).
const zlib = require("zlib");
const fs = require("fs");
const path = require("path");

function crc32(buf) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = [];
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (const b of buf) c = table[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function makePng(size) {
  // emerald background with a lighter "sprout" diamond band for recognizability
  const raw = Buffer.alloc(size * (size * 4 + 1));
  let off = 0;
  for (let y = 0; y < size; y++) {
    raw[off++] = 0; // filter none
    for (let x = 0; x < size; x++) {
      const dx = Math.abs(x - size / 2) / (size / 2);
      const dy = Math.abs(y - size * 0.62) / (size * 0.38);
      const inLeaf = dx + dy < 1;
      const stem = Math.abs(x - size / 2) < size * 0.05 && y > size * 0.6 && y < size * 0.9;
      let r = 6, g = 95, b = 70; // emerald-800 #065f46
      if (inLeaf) { r = 16; g = 185; b = 129; } // emerald-500
      if (stem) { r = 5; g = 150; b = 105; }
      raw[off++] = r; raw[off++] = g; raw[off++] = b; raw[off++] = 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const out = path.join(__dirname, "..", "public");
for (const size of [192, 512]) {
  fs.writeFileSync(path.join(out, `icon-${size}.png`), makePng(size));
  console.log(`wrote icon-${size}.png`);
}
