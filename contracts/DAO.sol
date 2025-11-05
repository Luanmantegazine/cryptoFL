// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Counters.sol";
import "hardhat/console.sol";

import "./DataTypes.sol";
import "./Requester.sol";
import "./Trainer.sol";
import "./JobContract.sol";

event JobContractCreated(address indexed job, uint256 indexed offerId, address indexed requester, address trainer);
event ProposalCreated(uint256 indexed id, address indexed proposer, string description, uint256 deadline);
event ProposalVoted(uint256 indexed id, address indexed voter, bool support, uint256 weight);
event ProposalExecuted(uint256 indexed id);

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
    Counters.Counter private proposalCounter;

    struct Proposal {
        uint256 id;
        address proposer;
        string description;
        uint256 deadline;
        uint256 forVotes;
        uint256 againstVotes;
        bool executed;
    }

    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;

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
        console.log("registerTrainer: ", msg.sender);

        Trainer newTrainer = new Trainer(msg.sender, _description, _specification);      

        //guarda o treinador na hash
        trainers[msg.sender] =  address(newTrainer);
        registeredTrainers.push(msg.sender);

        console.log("registerTrainer: End ", msg.sender, " TrainersCount=", registeredTrainers.length);

        return address(newTrainer);
    }

    //Requester
    function registerRequester ( ) external returns(address){
        require(
            !isRequester(msg.sender), "Requester already registered"
        );
        console.log("registerRequester: ", msg.sender);
        
        Requester newRequester = new Requester(msg.sender);

        //guarda o requisitante na hash
        requesters[msg.sender] =  address(newRequester);
        registeredRequesters.push(msg.sender);
        
        console.log("registerRequester: End", msg.sender,"RequestersCount=", registeredRequesters.length);

        return address(newRequester);
    }
    
    function matchTrainers (DataTypes.JobRequirements memory Requirements) external view returns(address  [] memory) {
        address [] memory candidates = new address[](Requirements.canditatesToReturn);
        uint256 candidatesCount = 0;
        uint256 i = 0;

        Log.Requirement(Requirements);

        while ((candidatesCount < Requirements.canditatesToReturn) && (i < registeredTrainers.length)) {
            address trainerAddr = registeredTrainers[i];

            Trainer trainer = Trainer(trainers[trainerAddr]);

            //Ve se da match entre o treinador e a oferta
            if (isMatch(Requirements, trainer)) {
                console.log("requestTrainer: MATCH ", trainerAddr, i);
                candidates[candidatesCount] = trainerAddr;
                candidatesCount = candidatesCount + 1;
            }
            else{
                console.log("requestTrainer: NOT match ", trainerAddr, i);
            }

            //Continua iteração
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

        // Example spec filtering: require RAM substring match when provided
        if (bytes(Requirements.description).length > 0) {
            bytes32 requiredDescHash = keccak256(bytes(Requirements.description));
            if (
                requiredDescHash != keccak256(bytes("")) &&
                requiredDescHash != keccak256(bytes(spec.cpu)) &&
                requiredDescHash != keccak256(bytes(spec.processor))
            ) {
                // Description acts as loose filter; if no match, reject.
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
        console.log("MakeOffer: ");

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

        Log.Offer(offer);
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

        console.log("DAO: AcceptOffer:", offerID, msg.sender);

        Trainer trainer = Trainer(trainers[msg.sender]);

        DataTypes.Offer memory offer = trainer.acceptOffer(offerID);
        if (offer.offerMaker != address(0)) {
            Requester offerMaker = Requester(requesters[offer.offerMaker]);
            JobContract newContract = new JobContract(offer);

            emit JobContractCreated(address(newContract), offer.ID, offer.offerMaker, offer.trainer);
            offerMaker.newContract(newContract);
            trainer.newContract(newContract);

            //Insere no hash de Contractos
            jobContracts[address(newContract)] = newContract;

            console.log("NewContract:", address(newContract),"OfferAccepted =",  offerID);
        }
    }

    function signJobContract(address addrContract) public payable {
        require(
            address(jobContracts[addrContract]) != address(0), "Job Contract not found"
            );

        JobContract job    = jobContracts[addrContract];
        console.log("signJobContract", msg.sender, msg.value);
        job.LogContract();

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
        job.LogContract();
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

    function createProposal(string calldata description, uint256 votingPeriod) external returns (uint256) {
        require(isMember(msg.sender), "Only DAO members");
        require(votingPeriod > 0, "Invalid period");

        uint256 proposalId = proposalCounter.current();
        proposalCounter.increment();

        Proposal storage p = proposals[proposalId];
        p.id = proposalId;
        p.proposer = msg.sender;
        p.description = description;
        p.deadline = block.timestamp + votingPeriod;

        emit ProposalCreated(proposalId, msg.sender, description, p.deadline);
        return proposalId;
    }

    function vote(uint256 proposalId, bool support) external {
        require(isMember(msg.sender), "Only DAO members");

        Proposal storage p = proposals[proposalId];
        require(p.deadline != 0, "Proposal not found");
        require(block.timestamp < p.deadline, "Voting closed");
        require(!hasVoted[proposalId][msg.sender], "Already voted");

        hasVoted[proposalId][msg.sender] = true;

        if (support) {
            p.forVotes += 1;
        } else {
            p.againstVotes += 1;
        }

        emit ProposalVoted(proposalId, msg.sender, support, 1);
    }

    function executeProposal(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(p.deadline != 0, "Proposal not found");
        require(block.timestamp >= p.deadline, "Voting not finished");
        require(!p.executed, "Already executed");
        require(p.forVotes > p.againstVotes, "Proposal rejected");

        p.executed = true;
        emit ProposalExecuted(proposalId);
    }

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