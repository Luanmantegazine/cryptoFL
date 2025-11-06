// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Counters.sol";
// import "hardhat/console.sol"; // Removido

import "./DataTypes.sol";
import "./Requester.sol";
import "./Trainer.sol";
import "./JobContract.sol";

event JobContractCreated(address indexed job, uint256 indexed offerId, address indexed requester, address trainer);
// Eventos de proposta removidos

contract DAO {
    // Add the library methods
    using Counters for Counters.Counter;

    //Treinadores
    mapping(address => address) trainers;
    address[] public registeredTrainers;

    //Requisitantes
    mapping(address => address) requesters;
    address[] public registeredRequesters;

    //jobContracts Contrats
    mapping(address => JobContract) jobContracts;

    Counters.Counter UID;
    // Struct, Mappings e Counter de Proposta removidos

    function nextID() private returns(uint256) {
       uint256 ID = UID.current();
       UID.increment();
       return ID;
    }

    // Trainer
    function registerTrainer (string memory _description, DataTypes.Specification memory _specification ) external returns(address){
        require(
            !isTrainer(msg.sender), "Trainer already registered"
        );
        // console.log("registerTrainer: ", msg.sender); // Removido

        Trainer newTrainer = new Trainer(msg.sender, _description, _specification);

        //guarda o treinador na hash
        trainers[msg.sender] =  address(newTrainer);
        registeredTrainers.push(msg.sender);

        // console.log("registerTrainer: End ", msg.sender, " TrainersCount=", registeredTrainers.length); // Removido

        return address(newTrainer);
    }

    //Requester
    function registerRequester ( ) external returns(address){
        require(
            !isRequester(msg.sender), "Requester already registered"
        );
        // console.log("registerRequester: ", msg.sender); // Removido

        Requester newRequester = new Requester(msg.sender);

        //guarda o requisitante na hash
        requesters[msg.sender] =  address(newRequester);
        registeredRequesters.push(msg.sender);

        // console.log("registerRequester: End", msg.sender,"RequestersCount=", registeredRequesters.length); // Removido

        return address(newRequester);
    }

    function matchTrainers (DataTypes.JobRequirements memory Requirements) external view returns(address  [] memory) {
        address [] memory candidates = new address[](Requirements.canditatesToReturn);
        uint256 candidatesCount = 0;
        uint256 i = 0;

        // Log.Requirement(Requirements); // Removido

        while ((candidatesCount < Requirements.canditatesToReturn) && (i < registeredTrainers.length)) {
            address trainerAddr = registeredTrainers[i];
            Trainer trainer = Trainer(trainers[trainerAddr]);

            if (isMatch(Requirements, trainer)) {
                // console.log("requestTrainer: MATCH ", trainerAddr, i); // Removido
                candidates[candidatesCount] = trainerAddr;
                candidatesCount = candidatesCount + 1;
            }
            // else{
                // console.log("requestTrainer: NOT match ", trainerAddr, i); // Removido
            // }
            i = i + 1;
        }
        return candidates;
    }

    function isMatch(DataTypes.JobRequirements memory Requirements, Trainer trainer) internal view returns (bool){
        (int trainerRating, string[] memory trainerTags, DataTypes.Specification memory spec) = trainer.getProfile();

        if (Requirements.minRating > 0 && trainerRating < int(Requirements.minRating)) {
            return false;
        }

        if (Requirements.tags.length > 0) {
            for (uint256 i = 0; i < Requirements.tags.length; i++) {
                if (!containsTag(trainerTags, Requirements.tags[i])) {
                    return false;
                }
            }
        }

        if (bytes(Requirements.description).length > 0) {
            bytes32 requiredDescHash = keccak256(bytes(Requirements.description));
            if (
                requiredDescHash != keccak256(bytes("")) &&
                requiredDescHash != keccak256(bytes(spec.cpu)) &&
                requiredDescHash != keccak256(bytes(spec.processor))
            ) {
                return false;
            }
        }
        return true;
    }

    function containsTag(string[] memory pool, string memory tag) internal pure returns (bool) {
        bytes32 expected = keccak256(bytes(tag));
        for (uint256 i = 0; i < pool.length; i++) {
            if (keccak256(bytes(pool[i])) == expected) {
                return true;
            }
        }
        return false;
    }

    function MakeOffer(
        string memory description,
        bytes32 modelCIDHash,
        bytes32 serverEndpointHash,
        bytes calldata encryptedMetadata,
        uint256 valueByUpdate,
        uint256 numberOfUpdates,
        address trainerAddr
    ) external {
        require(
            isRequester(msg.sender), "Requester not registered"
        );
        require(
            isTrainer(trainerAddr), "Trainer not found"
        );
        // console.log("MakeOffer: "); // Removido

        Trainer trainer = Trainer(trainers[trainerAddr]);

        DataTypes.Offer memory offer;
        offer.ID              = nextID();
        offer.description     = description;
        offer.modelCIDHash    = modelCIDHash;
        offer.serverEndpointHash = serverEndpointHash;
        offer.encryptedMetadata = encryptedMetadata;
        offer.valueByUpdate   = valueByUpdate;
        offer.numberOfUpdates = numberOfUpdates;
        offer.offerMaker      = msg.sender;
        offer.trainer         = trainerAddr;

        // Log.Offer(offer); // Removido
        trainer.newOffer(offer);
    }

    function getPendingOffers() external view returns(DataTypes.Offer [] memory) {
        require(
            isTrainer(msg.sender), "Just registered trainners can check pending offer"
        );
        Trainer trainer = Trainer(trainers[msg.sender]);
        return trainer.getPendingOffers();
    }

    function AcceptOffer(uint256 offerID) external {
        require(
            isTrainer(msg.sender), "Just registered trainners can accept an offer"
        );
        // console.log("DAO: AcceptOffer:", offerID, msg.sender); // Removido

        Trainer trainer = Trainer(trainers[msg.sender]);

        DataTypes.Offer memory offer = trainer.acceptOffer(offerID);
        if (offer.offerMaker != address(0)) {
            Requester offerMaker = Requester(requesters[offer.offerMaker]);
            JobContract newContract = new JobContract(offer);

            emit JobContractCreated(address(newContract), offer.ID, offer.offerMaker, offer.trainer);
            offerMaker.newContract(newContract);
            trainer.newContract(newContract);

            jobContracts[address(newContract)] = newContract;
            // console.log("NewContract:", address(newContract),"OfferAccepted =",  offerID); // Removido
        }
    }

    function signJobContract(address addrContract) public payable {
        require(
            address(jobContracts[addrContract]) != address(0), "Job Contract not found"
            );

        JobContract job    = jobContracts[addrContract];
        // console.log("signJobContract", msg.sender, msg.value); // Removido
        // job.LogContract(); // Removido

        bool bIsTrainer    = (msg.sender == job.trainerAddr());
        bool bIsOfferMaker = (msg.sender == job.offerMakerAddr());

        require(
            ((bIsTrainer) || (bIsOfferMaker)), "Just the trainer and the OfferMaker can assign the contract"
        );

        if (bIsOfferMaker) {
            require(
                msg.value == job.totalAmount(), "Should be sent the exactly value to be locked"
            );
            job.deposit{value: msg.value}();
        }

        job.sign(msg.sender);
        // job.LogContract(); // Removido
    }

    function releaseJobPayment(address addrContract, address payable recipient) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.offerMakerAddr() || msg.sender == job.trainerAddr(),
            "Unauthorized release"
        );
        job.releaseToTrainer(recipient);
    }

    function publishGlobalModel(address addrContract, bytes32 cidHash, bytes calldata encryptedCid) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.offerMakerAddr() || msg.sender == job.trainerAddr(),
            "Unauthorized publisher"
        );
        job.publishGlobalModel(cidHash, encryptedCid);
    }

    function recordClientUpdate(address addrContract, bytes32 cidHash, bytes calldata encryptedCid) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.trainerAddr() || msg.sender == job.offerMakerAddr(),
            "Unauthorized reporter"
        );
        job.recordClientUpdate(cidHash, encryptedCid);
    }

    // Funções de Governança (createProposal, vote, executeProposal) removidas

    function isTrainer(address trainer) internal view returns (bool){
        return (trainers[trainer] != address(0));
    }

    function isMember(address account) internal view returns (bool) {
        return isTrainer(account) || isRequester(account);
    }

    function isJob(address addr) public view returns (bool) {
    return address(jobContracts[addr]) != address(0);
    }

    function isRequester(address requester) internal view returns (bool){
        return (requesters[requester] != address(0));
    }
}