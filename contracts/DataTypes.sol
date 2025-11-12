// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

library DataTypes {
    enum Status { None,
                  WaitingSignatures,
                  WaitingTrainerSignature,
                  WaitingRequesterSignature,
                  Signed,
                  Declined,
                  Fulfilled }

    function StatusToStr(Status status) public pure returns(string memory){
        if (status == Status.WaitingSignatures){
            return "WaitingSignatures";
        }
        if (status == Status.WaitingTrainerSignature){
            return "WaitingTrainerSignature";
        }
        if (status == Status.WaitingRequesterSignature){
            return "WaitingRequesterSignature";
        }
        if (status == Status.Signed){
            return "Signed";
        }
        if (status == Status.Fulfilled){
            return "Fulfilled";
        }
        if (status == Status.Declined){
            return "Declined";
        }
        return "";
    }

    struct Evaluation {
        string comment;
        int rating;
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
