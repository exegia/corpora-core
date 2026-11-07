import Foundation
import XCTest

@testable import CorporaTypes

final class CodableRoundTripTests: XCTestCase {
    func testNodeUnionRoundTripsThroughTaggedJSON() throws {
        let block = Block(
            id: 7,
            kind: "text:paragraph",
            text: "In the beginning",
            metadata: Metadata(
                title: nil, creators: [], language: nil, publisher: nil, date: nil,
                description: nil, identifier: nil, rights: nil, subjects: [], properties: []
            )
        )
        let node = Node.block(block)

        let data = try JSONEncoder().encode(node)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["type"] as? String, "block")

        let decoded = try JSONDecoder().decode(Node.self, from: data)
        XCTAssertEqual(decoded, node)
    }

    func testEnumUsesWireValues() throws {
        let data = try JSONEncoder().encode(ProjectStatus.readyForReview)
        XCTAssertEqual(String(data: data, encoding: .utf8), "\"ready-for-review\"")
    }

    func testCodingKeysMapSnakeCase() throws {
        let commit = CorpusCommit(
            id: UUID(), documentId: UUID(), sha: "abc123", message: "init",
            authorName: "Ada", authorEmail: nil, branch: nil, committedAt: nil
        )
        let data = try JSONEncoder().encode(commit)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNotNil(json["author_name"])
        XCTAssertNil(json["authorName"])
    }
}
