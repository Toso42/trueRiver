export const EQ_BANDS = [
  { frequency: 31, label: '31' },
  { frequency: 62, label: '62' },
  { frequency: 125, label: '125' },
  { frequency: 250, label: '250' },
  { frequency: 500, label: '500' },
  { frequency: 1000, label: '1k' },
  { frequency: 2000, label: '2k' },
  { frequency: 4000, label: '4k' },
  { frequency: 8000, label: '8k' },
  { frequency: 16000, label: '16k' },
];

export function getSpectrumBandRanges(sampleRate) {
  const nyquist = sampleRate / 2;
  return EQ_BANDS.map((band, index) => {
    const previous = EQ_BANDS[index - 1]?.frequency || band.frequency / 1.8;
    const next = EQ_BANDS[index + 1]?.frequency || Math.min(nyquist, band.frequency * 1.8);
    return {
      min: Math.max(0, Math.sqrt(previous * band.frequency)),
      max: Math.min(nyquist, Math.sqrt(next * band.frequency)),
    };
  });
}

export function readSpectrumLevels(analyser, byteFrequencyData) {
  if (!analyser || !byteFrequencyData) {
    return EQ_BANDS.map(() => 0);
  }

  analyser.getByteFrequencyData(byteFrequencyData);
  const sampleRate = analyser.context?.sampleRate || 44100;
  const ranges = getSpectrumBandRanges(sampleRate);
  const hzPerBin = (sampleRate / 2) / Math.max(byteFrequencyData.length, 1);

  return ranges.map((range) => {
    const startIndex = Math.max(0, Math.floor(range.min / hzPerBin));
    const endIndex = Math.min(byteFrequencyData.length - 1, Math.ceil(range.max / hzPerBin));
    let total = 0;
    let count = 0;
    for (let index = startIndex; index <= endIndex; index += 1) {
      total += byteFrequencyData[index] || 0;
      count += 1;
    }
    return count ? Math.min(total / count / 255, 1) : 0;
  });
}
