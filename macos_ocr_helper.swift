import Vision
import AppKit
import Foundation
let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg  = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
for obs in (req.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    let x = b.origin.x * Double(cg.width)
    let y = (1 - b.origin.y - b.size.height) * Double(cg.height)
    let w = b.size.width  * Double(cg.width)
    let h = b.size.height * Double(cg.height)
    print("\(x)|\(y)|\(w)|\(h)|\(top.string)")
}
