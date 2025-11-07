// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

import "./DataTypes.sol";

contract JobContract is ReentrancyGuard {
    string private description;
    uint256 private valueByUpdate;
    uint256 private numberOfUpdates;
    uint256 private updatesDone;

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
    DataTypes.UpdateRecord[] private updateLog;
    DataTypes.GlobalModelRecord[] private globalModelLog;

    event FundsLocked(uint256 amount);
    event ClientUpdateRecorded(
        bytes32 indexed updateHash,
        address indexed caller,
        uint256 index,
        uint256 approvedUpdates,
        bytes encryptedPointer
    );
    event ClientUpdateApproved(bytes32 indexed updateHash, uint256 index, uint256 approvedUpdates, uint256 escrowedAmount);
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
        Status = DataTypes.Status.WaitingSignatures;
    }

    function totalAmount() public view returns (uint256) {
        return (valueByUpdate * numberOfUpdates);
    }

    function deposit() external payable onlyDAO {
        lockedAmount += msg.value;
        require(lockedAmount <= totalAmount(), "Deposit exceeds contract value");
        emit FundsLocked(msg.value);
    }

    function recordClientUpdate(bytes32 cidHash, bytes calldata encryptedCid) external onlyAuthorizedReporter {
        require(cidHash != bytes32(0), "Invalid hash");
        require(!receivedUpdate[cidHash], "Update already recorded");
        require(updateLog.length < numberOfUpdates + 5, "Too many pending updates");

        receivedUpdate[cidHash] = true;
        clientUpdateHashes.push(cidHash);

        updateLog.push(
            DataTypes.UpdateRecord({
                cidHash: cidHash,
                reporter: msg.sender,
                approved: false,
                encryptedPointer: encryptedCid,
                timestamp: block.timestamp
            })
        );

        emit ClientUpdateRecorded(cidHash, msg.sender, updateLog.length - 1, updatesDone, encryptedCid);
    }

    function publishGlobalModel(bytes32 cidHash, bytes calldata encryptedCid) external onlyDAO {
        latestModelHash = cidHash;
        globalModelLog.push(
            DataTypes.GlobalModelRecord({
                cidHash: cidHash,
                encryptedPointer: encryptedCid,
                round: updatesDone,
                timestamp: block.timestamp
            })
        );

        emit GlobalModelUpdated(cidHash, updatesDone, encryptedCid);
    }

    function approveClientUpdate(uint256 index) external onlyDAO {
        require(index < updateLog.length, "Invalid update index");
        require(updatesDone < numberOfUpdates, "All updates approved");

        DataTypes.UpdateRecord storage entry = updateLog[index];
        require(!entry.approved, "Already approved");

        entry.approved = true;

        require(availableAmount + valueByUpdate <= lockedAmount, "Insufficient escrow");
        availableAmount += valueByUpdate;
        updatesDone += 1;

        if (updatesDone == numberOfUpdates) {
            Status = DataTypes.Status.Fulfilled;
        }

        emit ClientUpdateApproved(entry.cidHash, index, updatesDone, availableAmount);
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

    function totalSubmittedUpdates() external view returns (uint256) {
        return updateLog.length;
    }

    function getUpdate(uint256 index) external view returns (bytes32, address, bool, bytes memory, uint256) {
        require(index < updateLog.length, "Invalid update index");

        DataTypes.UpdateRecord storage entry = updateLog[index];
        return (entry.cidHash, entry.reporter, entry.approved, entry.encryptedPointer, entry.timestamp);
    }

    function clientUpdateHashesLength() external view returns (uint256) {
        return clientUpdateHashes.length;
    }

    function globalModelHistoryLength() external view returns (uint256) {
        return globalModelLog.length;
    }

    function getGlobalModel(uint256 index) external view returns (bytes32, uint256, uint256, bytes memory) {
        require(index < globalModelLog.length, "Invalid model index");

        DataTypes.GlobalModelRecord storage entry = globalModelLog[index];
        return (entry.cidHash, entry.round, entry.timestamp, entry.encryptedPointer);
    }
}

