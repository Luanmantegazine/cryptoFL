// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/utils/Counters.sol";
import "./DataTypes.sol";
import "./JobContract.sol";

contract Trainer {
    string   public      description;
    string[] public      tags;
    int      public      rating;
    DataTypes.Evaluation[]  public  evaluations;
    DataTypes.Specification public  specification;
    string public dataPreviewCID;

    uint256[] internal pendingOffersIDs;
    mapping(uint256 => DataTypes.Offer) private pendingOffers;

    address[] internal jobsAddress;
    mapping(address => JobContract) private jobContracts;

    address public owner;
    address public DAO;

    constructor(address payable ownerAddress, string memory _description, DataTypes.Specification memory _specification) {
        DAO    = msg.sender;
        owner         = ownerAddress;
        description   = _description;
        specification = _specification;
        rating        = 10;
    }

    modifier onlyOwner {
      require(msg.sender == owner,  "Only owner");
      _;
    }

    modifier onlyDAO {
      require(msg.sender == DAO, "Only DAO");
      _;
    }

    function setDescription (string memory _description) external onlyOwner {
        description = _description;
    }

    function setTags (string[] memory  _tags) external onlyOwner {
        tags = _tags;
    }

    function newOffer(DataTypes.Offer memory offer) external onlyDAO {
        insertOffer(offer);
    }

    function newContract(JobContract job) external onlyDAO {
        insertContract(job);
    }

    function acceptOffer(uint256 offerID) external onlyDAO returns(DataTypes.Offer memory) {
        DataTypes.Offer memory offer;
        if(containsOffer(offerID)){
            offer = pendingOffers[offerID];
            deleteOffer(offerID);
        }
        return offer;
    }

   function getPendingOffers() external view onlyDAO returns(uint256 [] memory) {
    return pendingOffersIDs;
    }

    function containsOffer(uint256 offerID) public view returns (bool){
        return (pendingOffers[offerID].trainer != address(0));
    }

    function getProfile() external view returns (int, string[] memory, DataTypes.Specification memory) {
        return (rating, tags, specification);
    }

    function getOfferDetails(uint256 offerID) external view onlyDAO returns (DataTypes.Offer memory) {
    require(containsOffer(offerID), "Offer not found");
    return pendingOffers[offerID];
    }

    //FUNÇÕES AUXILIARES
    function insertOffer(DataTypes.Offer memory offer) internal {
        pendingOffers[offer.ID] = offer;
        pendingOffersIDs.push(offer.ID);
        // console.log("insertOffer:" , offer.ID, " Count pending offers =", pendingOffersIDs.length); // Removido
    }

    function insertContract(JobContract job) internal {
        jobContracts[address(job)] = job;
        jobsAddress.push(address(job));
        // console.log("insertContract:" ,address(job), " Count jobContracts =", jobsAddress.length); // Removido
    }

    function deleteOffer(uint256 offerID) internal {
        uint256 idxOffer = 0;
        bool    bFound   = false;
        while ((idxOffer < pendingOffersIDs.length) && (!bFound)){
            if (pendingOffersIDs[idxOffer] == offerID) {
                bFound = true;
                break;
            }
            idxOffer++;
        }

        if (bFound) {
            pendingOffersIDs[idxOffer] = pendingOffersIDs[pendingOffersIDs.length-1];
            pendingOffersIDs.pop();
            delete pendingOffers[offerID];
        }
    }
}