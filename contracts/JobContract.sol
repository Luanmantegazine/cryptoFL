// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

// import "hardhat/console.sol"; // Removido
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

import "./DataTypes.sol";

contract JobContract is ReentrancyGuard {
    string private description;
    uint256 private valueByUpdate;
    uint256 private numberOfUpdates;
    uint256 private updatesDone;
    uint256 private withdrawAmount;

    bytes32 public initialModelHash;
    bytes32 public initialServerEndpointHash;
    bytes public initialMetadata;

    bytes32 public latestModelHash;

    DataTypes.Status public Status;
    address public offerMaker;
    address public trainer;
    address public DAOManager;

    uint256 public lockedAmount;
    uint256 public availableAmount;

    bytes32[] public clientUpdateHashes;
    mapping(bytes32 => bool) public receivedUpdate;

    event FundsLocked(uint256 amount);
    event ClientUpdateRecorded(
        bytes32 indexed updateHash,
        address indexed caller,
        uint256 updatesDone,
        uint256 escrowedAmount,
        bytes encryptedPointer
    );
    event GlobalModelUpdated(bytes32 indexed modelHash, uint256 updatesDone, bytes encryptedPointer);
    event PayoutReleased(address indexed to, uint256 value);

    modifier onlyDAO {
        require(msg.sender == DAOManager, "Only DAO");
        _;
    }

    modifier onlyAuthorizedReporter {
        require(
            msg.sender == DAOManager || msg.sender == offerMaker || msg.sender == trainer,
            "Not authorized"
        );
        _;
    }

    constructor(DataTypes.Offer memory offer) {
        DAOManager = msg.sender;
        offerMaker = offer.offerMaker;
        trainer = offer.trainer;
        description = offer.description;
        valueByUpdate = offer.valueByUpdate;
        numberOfUpdates = offer.numberOfUpdates;
        initialModelHash = offer.modelCIDHash;
        initialServerEndpointHash = offer.serverEndpointHash;
        initialMetadata = offer.encryptedMetadata;
        updatesDone = 0;
        lockedAmount = 0;
        availableAmount = 0;
        withdrawAmount = 0;
        Status = DataTypes.Status.WaitingSignatures;
        // console.log("JobContract : Trainer = ", trainer, offerMaker); // Removido
    }

    // function LogContract() public view { // Removido
        // ...
    // }

    function totalAmount() public view returns (uint256) {
        return (valueByUpdate * numberOfUpdates);
    }

    function deposit() external payable onlyDAO {
        lockedAmount += msg.value;
        require(lockedAmount <= totalAmount(), "Deposit exceeds contract value");
        emit FundsLocked(msg.value);
    }

    function recordClientUpdate(bytes32 cidHash, bytes calldata encryptedCid) external onlyAuthorizedReporter {
        require(!receivedUpdate[cidHash], "Update already recorded");
        require(updatesDone < numberOfUpdates, "All updates completed");

        receivedUpdate[cidHash] = true;
        clientUpdateHashes.push(cidHash);
        updatesDone += 1;
        availableAmount += valueByUpdate;
        withdrawAmount += valueByUpdate;
        if (updatesDone == numberOfUpdates) {
            Status = DataTypes.Status.Fulfilled;
        }

        emit ClientUpdateRecorded(cidHash, msg.sender, updatesDone, availableAmount, encryptedCid);
    }

    function publishGlobalModel(bytes32 cidHash, bytes calldata encryptedCid) external onlyDAO {
        latestModelHash = cidHash;
        emit GlobalModelUpdated(cidHash, updatesDone, encryptedCid);
    }

    function releaseToTrainer(address payable recipient) external onlyDAO nonReentrant returns (uint256) {
        if (recipient == address(0)) {
            recipient = payable(trainer);
        }

        uint256 amount = availableAmount;
        require(amount > 0, "No funds available");
        require(amount <= address(this).balance, "Insufficient balance");

        availableAmount = 0;
        lockedAmount -= amount;

        (bool ok, ) = recipient.call{value: amount}("");
        require(ok, "Transfer failed");
        emit PayoutReleased(recipient, amount);
        return amount;
    }

    function sign(address signer) public onlyDAO {
        // console.log("sign: Signer =", signer, trainer, offerMaker); // Removido
        require(
            (Status != DataTypes.Status.Signed), "JobContract already signed"
            );
        bool bIsTrainer    = (signer == trainer);
        bool bIsOfferMaker = (signer == offerMaker);
        if (bIsTrainer) {
            if (Status == DataTypes.Status.WaitingSignatures) {
                Status = DataTypes.Status.WaitingRequesterSignature;
            }
            else{
               Status = DataTypes.Status.Signed;
            }
        }

        if (bIsOfferMaker) {
            if (Status == DataTypes.Status.WaitingSignatures) {
                Status = DataTypes.Status.WaitingTrainerSignature;
            }
            else{
               Status = DataTypes.Status.Signed;
            }
        }
    }

    function trainerAddr() public view returns (address){
        return trainer;
    }

    function offerMakerAddr() public view returns (address){
        return offerMaker;
    }

    function getInitialServerEndpointHash() public view returns (bytes32) {
        return initialServerEndpointHash;
    }

    function getInitialMetadata() external view returns (bytes memory) {
        return initialMetadata;
    }
}