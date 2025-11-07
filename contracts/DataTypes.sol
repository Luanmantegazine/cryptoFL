// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

library DataTypes {
    enum Status {
        None,
        WaitingSignatures,
        WaitingTrainerSignature,
        WaitingRequesterSignature,
        Signed,
        Declined,
        Fulfilled
    }

    struct Evaluation {
        string comment;
        int256 rating;
    }

    struct UpdateRecord {
        bytes32 cidHash;
        address reporter;
        bool approved;
        bytes encryptedPointer;
        uint256 timestamp;
    }

    struct GlobalModelRecord {
        bytes32 cidHash;
        bytes encryptedPointer;
        uint256 round;
        uint256 timestamp;
    }

    struct Specification {
        string processor;
        string ram;
        string cpu;
    }

    struct Offer {
        uint256 ID;
        string description;
        bytes32 modelCIDHash;
        bytes32 serverEndpointHash;
        bytes encryptedMetadata;
        uint256 valueByUpdate;
        uint256 numberOfUpdates;
        address offerMaker;
        address trainer;
    }

    struct JobRequirements {
        string description;
        uint256 valueByUpdate;
        uint256 minRating;
        string[] tags;
        uint256 canditatesToReturn;
    }
}

