// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "tailtag_clerk",
    platforms: [
        .iOS("17.0")
    ],
    products: [
        .library(name: "tailtag-clerk", targets: ["tailtag_clerk"])
    ],
    dependencies: [
        .package(name: "FlutterFramework", path: "../FlutterFramework"),
        // The pin is exact on purpose. ClerkKit only, never ClerkKitUI.
        .package(url: "https://github.com/clerk/clerk-ios", exact: "1.6.1"),
    ],
    targets: [
        .target(
            name: "tailtag_clerk",
            dependencies: [
                .product(name: "FlutterFramework", package: "FlutterFramework"),
                .product(name: "ClerkKit", package: "clerk-ios"),
            ]
        )
    ]
)
